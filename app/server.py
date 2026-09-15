"""Local personal-needs application server. Run: python -m app.server"""
import argparse
import csv
import io
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .db import DEFAULT_DB, ROOT, connect, initialize
from .config import load_local_env, configured_database_path, configured_host, configured_port

FEELINGS = {"烦", "浪费时间", "无聊", "重复", "困惑", "容易忘", "容易出错", "不确定", "很想自动化", "其他"}
TEXT_FIELDS = {
    "context": 200, "problem": 4000, "feeling_note": 500,
    "current_process": 4000, "pain_point": 4000, "current_solution": 4000,
    "solution_problem": 4000, "desired_state": 4000, "input": 2000, "output": 2000,
}
CHOICE_FIELDS = {
    "repeatability": {"一次性", "偶尔", "每月", "每周", "每天", "高频", None},
    "standardizable": {"是", "部分可以", "不确定", "否", None},
}
SCORE_FIELDS = ("pain_score", "frequency_score", "time_cost_score", "automation_potential", "usage_intent")
SCENES = {"学习", "科研", "编程", "摄影", "生活", "文件管理", "信息整理", "时间管理", "AI", "社交", "其他"}
RECORD_PATH = re.compile(r"^/api/records/(\d+)$")
THEME_PATH = re.compile(r"^/api/themes/(\d+)$")
THEME_PROMPT_PATH = re.compile(r"^/api/themes/(\d+)/prompt$")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        target = urlsplit(self.path)
        path = target.path
        if path == "/":
            self.respond(200, (ROOT / "app" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path in {"/manifest.webmanifest", "/service-worker.js", "/cloud-config.js", "/cloud.js", "/icons/app-icon.svg"}:
            static_files = {
                "/manifest.webmanifest": (ROOT / "app" / "manifest.webmanifest", "application/manifest+json; charset=utf-8"),
                "/service-worker.js": (ROOT / "app" / "service-worker.js", "text/javascript; charset=utf-8"),
                "/cloud-config.js": (ROOT / "app" / "cloud-config.js", "text/javascript; charset=utf-8"),
                "/cloud.js": (ROOT / "app" / "cloud.js", "text/javascript; charset=utf-8"),
                "/icons/app-icon.svg": (ROOT / "app" / "icons" / "app-icon.svg", "image/svg+xml"),
            }
            file_path, content_type = static_files[path]
            if not file_path.is_file():
                self.respond_json(404, {"error": "Not found"})
                return
            self.respond(200, file_path.read_bytes(), content_type, {"Cache-Control": "public, max-age=3600"})
        elif path == "/api/health":
            self.get_health()
        elif path == "/api/records":
            self.list_records(parse_qs(target.query))
        elif path == "/api/tags":
            self.list_tags()
        elif path == "/api/analytics":
            self.get_analytics()
        elif path == "/api/themes":
            self.list_themes()
        elif path == "/api/review/weekly":
            self.get_weekly_review()
        elif match := THEME_PROMPT_PATH.match(path):
            self.get_theme_prompt(int(match.group(1)), parse_qs(target.query))
        elif match := RECORD_PATH.match(path):
            self.get_record(int(match.group(1)))
        elif path == "/api/export/json":
            self.export_json()
        elif path == "/api/export/csv":
            self.export_csv()
        else:
            self.respond_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/tags":
            self.create_tag()
            return
        if path == "/api/themes":
            self.create_theme()
            return
        if path != "/api/records":
            self.respond_json(404, {"error": "Not found"})
            return
        data = self.read_json()
        if data is None:
            return
        cleaned = validate_record(data, partial=False)
        if "error" in cleaned:
            self.respond_json(422, cleaned)
            return
        encoded_feelings = json.dumps(cleaned.pop("feeling"), ensure_ascii=False)
        conn = connect(self.server.db_path)
        try:
            if cleaned["tag_ids"]:
                placeholders = ",".join("?" for _ in cleaned["tag_ids"])
                found = conn.execute(f"SELECT COUNT(*) FROM tags WHERE id IN ({placeholders})", cleaned["tag_ids"]).fetchone()[0]
                if found != len(cleaned["tag_ids"]):
                    self.respond_json(422, {"error": "包含不存在的标签"})
                    return
            with conn:
                cursor = conn.execute(
                    """INSERT INTO records
                       (context, problem, original_context, original_problem,
                        feeling, original_feeling, feeling_note)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (cleaned["context"], cleaned["problem"], cleaned["context"], cleaned["problem"],
                     encoded_feelings, encoded_feelings, cleaned["feeling_note"]),
                )
            self.respond_json(201, {"id": cursor.lastrowid, "message": "已记下"})
        except sqlite3.Error:
            self.respond_json(500, {"error": "保存失败，请稍后重试"})
        finally:
            conn.close()

    def do_PUT(self):
        match = RECORD_PATH.match(urlsplit(self.path).path)
        if not match:
            self.respond_json(404, {"error": "Not found"})
            return
        data = self.read_json()
        if data is None:
            return
        cleaned = validate_record(data, partial=True)
        if "error" in cleaned:
            self.respond_json(422, cleaned)
            return
        record_id = int(match.group(1))
        values = {name: cleaned.get(name, "") for name in TEXT_FIELDS}
        values["feeling"] = json.dumps(cleaned["feeling"], ensure_ascii=False)
        values["repeatability"] = cleaned.get("repeatability") or None
        values["standardizable"] = cleaned.get("standardizable") or None
        values["scene"] = cleaned["scene"]
        values["related_need"] = cleaned["related_need"]
        for name in SCORE_FIELDS:
            values[name] = cleaned[name]
        values["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        assignments = ", ".join(f"{name} = ?" for name in values)
        conn = connect(self.server.db_path)
        try:
            if cleaned["tag_ids"]:
                placeholders = ",".join("?" for _ in cleaned["tag_ids"])
                found = conn.execute(f"SELECT COUNT(*) FROM tags WHERE id IN ({placeholders})", cleaned["tag_ids"]).fetchone()[0]
                if found != len(cleaned["tag_ids"]):
                    self.respond_json(422, {"error": "包含不存在的标签"})
                    return
            if cleaned["related_need"] is not None:
                if conn.execute("SELECT 1 FROM themes WHERE id = ?", (cleaned["related_need"],)).fetchone() is None:
                    self.respond_json(422, {"error": "选择的需求主题不存在"})
                    return
            with conn:
                cursor = conn.execute(f"UPDATE records SET {assignments} WHERE id = ?", (*values.values(), record_id))
                if cursor.rowcount:
                    conn.execute("DELETE FROM record_tags WHERE record_id = ?", (record_id,))
                    conn.executemany("INSERT INTO record_tags(record_id, tag_id) VALUES (?, ?)", [(record_id, tag_id) for tag_id in cleaned["tag_ids"]])
            if cursor.rowcount == 0:
                self.respond_json(404, {"error": "这条记录不存在"})
            else:
                self.respond_json(200, {"id": record_id, "message": "修改已保存"})
        except sqlite3.Error:
            self.respond_json(500, {"error": "保存失败，请稍后重试"})
        finally:
            conn.close()

    def do_DELETE(self):
        path = urlsplit(self.path).path
        if theme_match := THEME_PATH.match(path):
            self.delete_theme(int(theme_match.group(1)))
            return
        match = RECORD_PATH.match(path)
        if not match:
            self.respond_json(404, {"error": "Not found"})
            return
        conn = connect(self.server.db_path)
        try:
            with conn:
                cursor = conn.execute("DELETE FROM records WHERE id = ?", (int(match.group(1)),))
            if cursor.rowcount == 0:
                self.respond_json(404, {"error": "这条记录不存在"})
            else:
                self.respond(204, b"", "application/json")
        finally:
            conn.close()

    def get_health(self):
        conn = connect(self.server.db_path)
        try:
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            self.respond_json(200, {"ok": True, "phase": 8, "schema_version": version, "records": count})
        finally:
            conn.close()

    def list_records(self, query):
        search = clean_text(query.get("q", [""])[0], 200)
        sort = query.get("sort", ["latest"])[0]
        params = []
        where = ""
        if search:
            where = "WHERE context LIKE ? ESCAPE '\\' OR problem LIKE ? ESCAPE '\\' OR feeling_note LIKE ? ESCAPE '\\'"
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params = [f"%{escaped}%"] * 3
        conn = connect(self.server.db_path)
        try:
            rows = conn.execute(f"SELECT * FROM records {where}", params).fetchall()
            records = [record_dict(conn, row, compact=True) for row in rows]
            records.sort(key=sort_key(sort), reverse=sort != "oldest")
            self.respond_json(200, {"records": records, "count": len(records)})
        finally:
            conn.close()

    def get_record(self, record_id):
        conn = connect(self.server.db_path)
        try:
            row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                self.respond_json(404, {"error": "这条记录不存在"})
            else:
                self.respond_json(200, record_dict(conn, row))
        finally:
            conn.close()

    def list_tags(self):
        conn = connect(self.server.db_path)
        try:
            tags = [dict(row) for row in conn.execute("SELECT id, name, category FROM tags ORDER BY category, id")]
            self.respond_json(200, {"tags": tags})
        finally:
            conn.close()

    def create_tag(self):
        data = self.read_json()
        if data is None:
            return
        name = clean_text(data.get("name"), 40)
        if not name:
            self.respond_json(422, {"error": "请输入标签名称"})
            return
        conn = connect(self.server.db_path)
        try:
            with conn:
                conn.execute("INSERT OR IGNORE INTO tags(name, category) VALUES (?, 'custom')", (name,))
                row = conn.execute("SELECT id, name, category FROM tags WHERE name = ? AND category = 'custom'", (name,)).fetchone()
            self.respond_json(201, dict(row))
        finally:
            conn.close()

    def get_analytics(self):
        conn = connect(self.server.db_path)
        try:
            rows = conn.execute("SELECT * FROM records WHERE status != 'Archived'").fetchall()
            records = [record_dict(conn, row, compact=True) for row in rows]
            scored = [record for record in records if record["opportunity_score"] is not None]
            scenes = [dict(row) for row in conn.execute(
                """SELECT scene AS label, COUNT(*) AS value FROM records
                   WHERE status != 'Archived' GROUP BY scene ORDER BY value DESC, scene LIMIT 10"""
            )]
            problem_tags = [dict(row) for row in conn.execute(
                """SELECT tags.name AS label, COUNT(*) AS value FROM tags
                   JOIN record_tags ON record_tags.tag_id = tags.id
                   JOIN records ON records.id = record_tags.record_id
                   WHERE tags.category = 'problem' AND records.status != 'Archived'
                   GROUP BY tags.id ORDER BY value DESC, tags.name LIMIT 10"""
            )]

            def top(field):
                available = [record for record in records if record[field] is not None]
                return sorted(available, key=lambda record: (record[field], record["occurred_at"], record["id"]), reverse=True)[:3]

            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "summary": {
                    "total_records": len(records),
                    "scored_records": len(scored),
                    "scoring_completion": round(len(scored) / len(records) * 100) if records else 0,
                    "average_opportunity": round(sum(record["opportunity_score"] for record in scored) / len(scored)) if scored else None,
                },
                "scene_counts": scenes,
                "problem_tag_counts": problem_tags,
                "rankings": {
                    "pain": top("pain_score"),
                    "frequency": top("frequency_score"),
                    "automation": top("automation_potential"),
                    "opportunity": top("opportunity_score"),
                },
            }
            self.respond_json(200, payload)
        finally:
            conn.close()

    def list_themes(self):
        conn = connect(self.server.db_path)
        try:
            themes = []
            for row in conn.execute("SELECT * FROM themes ORDER BY updated_at DESC, id DESC"):
                records = [record_dict(conn, item, compact=True) for item in conn.execute(
                    "SELECT * FROM records WHERE related_need = ? ORDER BY occurred_at DESC, id DESC", (row["id"],)
                )]
                def average(field):
                    values = [record[field] for record in records if record[field] is not None]
                    return round(sum(values) / len(values), 1) if values else None
                theme = dict(row)
                theme.update({
                    "record_count": len(records),
                    "first_seen": min((record["occurred_at"] for record in records), default=None),
                    "last_seen": max((record["occurred_at"] for record in records), default=None),
                    "average_pain": average("pain_score"),
                    "average_time_cost": average("time_cost_score"),
                    "average_automation": average("automation_potential"),
                    "opportunity_score": average("opportunity_score"),
                    "records": records,
                })
                themes.append(theme)
            unassigned = conn.execute("SELECT COUNT(*) FROM records WHERE related_need IS NULL").fetchone()[0]
            self.respond_json(200, {"themes": themes, "unassigned_records": unassigned})
        finally:
            conn.close()

    def get_weekly_review(self):
        china = timezone(timedelta(hours=8))
        now = datetime.now(china)
        start_local = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=7)
        start_utc = start_local.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        end_utc = end_local.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        conn = connect(self.server.db_path)
        try:
            rows = conn.execute(
                """SELECT * FROM records WHERE occurred_at >= ? AND occurred_at < ?
                   AND status != 'Archived' ORDER BY occurred_at DESC, id DESC""", (start_utc, end_utc)
            ).fetchall()
            records = [record_dict(conn, row, compact=True) for row in rows]
            scenes = [dict(row) for row in conn.execute(
                """SELECT scene AS label, COUNT(*) AS value FROM records
                   WHERE occurred_at >= ? AND occurred_at < ? AND status != 'Archived'
                   GROUP BY scene ORDER BY value DESC, scene""", (start_utc, end_utc)
            )]
            problem_tags = [dict(row) for row in conn.execute(
                """SELECT tags.name AS label, COUNT(*) AS value FROM tags
                   JOIN record_tags ON record_tags.tag_id = tags.id
                   JOIN records ON records.id = record_tags.record_id
                   WHERE tags.category = 'problem' AND records.occurred_at >= ? AND records.occurred_at < ?
                   AND records.status != 'Archived' GROUP BY tags.id ORDER BY value DESC, tags.name""", (start_utc, end_utc)
            )]
            def top(field):
                available = [record for record in records if record[field] is not None]
                return sorted(available, key=lambda record: (record[field], record["occurred_at"], record["id"]), reverse=True)[:3]
            self.respond_json(200, {
                "week": {"start": start_local.date().isoformat(), "end": (end_local - timedelta(days=1)).date().isoformat()},
                "total_records": len(records),
                "scene_counts": scenes,
                "problem_tag_counts": problem_tags,
                "rankings": {
                    "pain": top("pain_score"),
                    "frequency": top("frequency_score"),
                    "automation": top("automation_potential"),
                    "opportunity": top("opportunity_score"),
                },
            })
        finally:
            conn.close()

    def create_theme(self):
        data = self.read_json()
        if data is None:
            return
        name = clean_text(data.get("name"), 120)
        description = clean_text(data.get("description"), 1000)
        if not name:
            self.respond_json(422, {"error": "请输入主题名称"})
            return
        conn = connect(self.server.db_path)
        try:
            with conn:
                cursor = conn.execute("INSERT INTO themes(name, description) VALUES (?, ?)", (name, description))
            self.respond_json(201, {"id": cursor.lastrowid, "name": name, "description": description})
        except sqlite3.IntegrityError:
            self.respond_json(409, {"error": "已经存在同名主题"})
        finally:
            conn.close()

    def delete_theme(self, theme_id):
        conn = connect(self.server.db_path)
        try:
            with conn:
                cursor = conn.execute("DELETE FROM themes WHERE id = ?", (theme_id,))
            if cursor.rowcount == 0:
                self.respond_json(404, {"error": "这个主题不存在"})
            else:
                self.respond(204, b"", "application/json")
        finally:
            conn.close()

    def get_theme_prompt(self, theme_id, query):
        conn = connect(self.server.db_path)
        try:
            theme = conn.execute("SELECT * FROM themes WHERE id = ?", (theme_id,)).fetchone()
            if theme is None:
                self.respond_json(404, {"error": "这个主题不存在"})
                return
            rows = conn.execute(
                "SELECT * FROM records WHERE related_need = ? ORDER BY occurred_at DESC, id DESC", (theme_id,)
            ).fetchall()
            records = [record_dict(conn, row) for row in rows]
            prompt, stats = build_codex_prompt(dict(theme), records)
            if query.get("download", [""])[0] == "1":
                self.respond(200, prompt.encode("utf-8"), "text/plain; charset=utf-8", {
                    "Content-Disposition": 'attachment; filename="codex-project-prompt.txt"'
                })
            else:
                self.respond_json(200, {"theme_id": theme_id, "theme_name": theme["name"], "prompt": prompt, "stats": stats})
        finally:
            conn.close()

    def export_json(self):
        conn = connect(self.server.db_path)
        try:
            payload = {
                "format": "personal-needs-export",
                "version": 1,
                "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "records": [record_dict(conn, row) for row in conn.execute("SELECT * FROM records ORDER BY id")],
                "themes": [dict(row) for row in conn.execute("SELECT * FROM themes ORDER BY id")],
                "tags": [dict(row) for row in conn.execute("SELECT * FROM tags ORDER BY id")],
                "record_tags": [dict(row) for row in conn.execute("SELECT * FROM record_tags ORDER BY record_id, tag_id")],
            }
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.respond(200, body, "application/json; charset=utf-8", {"Content-Disposition": 'attachment; filename="personal-needs.json"'})
        finally:
            conn.close()

    def export_csv(self):
        conn = connect(self.server.db_path)
        try:
            rows = [record_dict(conn, row) for row in conn.execute("SELECT * FROM records ORDER BY id")]
            output = io.StringIO(newline="")
            fields = list(rows[0].keys()) if rows else ["id", *TEXT_FIELDS, "feeling", "repeatability", "standardizable", "status", "occurred_at", "created_at", "updated_at", "tags"]
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                row = dict(row)
                row["feeling"] = " | ".join(row["feeling"])
                row["original_feeling"] = " | ".join(row.get("original_feeling", []))
                row["tags"] = " | ".join(tag["name"] for tag in row["tags"])
                writer.writerow(row)
            body = ("\ufeff" + output.getvalue()).encode("utf-8")
            self.respond(200, body, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="personal-needs.csv"'})
        finally:
            conn.close()

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.respond_json(400, {"error": "请求长度无效"})
            return None
        if length <= 0 or length > 64 * 1024:
            self.respond_json(400, {"error": "请求内容为空或过大"})
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.respond_json(400, {"error": "请求不是有效的 JSON"})
            return None
        if not isinstance(data, dict):
            self.respond_json(400, {"error": "请求格式无效"})
            return None
        return data

    def respond_json(self, status, payload):
        self.respond(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def respond(self, status, body, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def clean_text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ""


def validate_record(data, partial):
    result = {name: clean_text(data.get(name), limit) for name, limit in TEXT_FIELDS.items()}
    if not result["context"] or not result["problem"]:
        return {"error": "请填写当时在做什么，以及发生了什么"}
    feelings = data.get("feeling", [])
    if not isinstance(feelings, list) or len(feelings) > 10:
        return {"error": "感受格式无效"}
    result["feeling"] = list(dict.fromkeys(item for item in feelings if isinstance(item, str) and item in FEELINGS))
    for name, allowed in CHOICE_FIELDS.items():
        value = data.get(name) or None
        if value not in allowed:
            return {"error": f"{name} 选项无效"}
        result[name] = value
    scene = data.get("scene") or "其他"
    if scene not in SCENES:
        return {"error": "场景选项无效"}
    result["scene"] = scene
    for name in SCORE_FIELDS:
        value = data.get(name)
        if value in (None, ""):
            result[name] = None
        elif isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            return {"error": f"{name} 必须是 1–5 分"}
        else:
            result[name] = value
    tag_ids = data.get("tag_ids", [])
    if not isinstance(tag_ids, list) or len(tag_ids) > 50 or any(isinstance(value, bool) or not isinstance(value, int) for value in tag_ids):
        return {"error": "标签格式无效"}
    result["tag_ids"] = list(dict.fromkeys(tag_ids))
    related_need = data.get("related_need")
    if related_need in (None, ""):
        result["related_need"] = None
    elif isinstance(related_need, bool) or not isinstance(related_need, int):
        return {"error": "需求主题格式无效"}
    else:
        result["related_need"] = related_need
    return result


def record_dict(conn, row, compact=False):
    result = dict(row)
    result["feeling"] = json.loads(result["feeling"])
    result["original_feeling"] = json.loads(result["original_feeling"])
    tags = conn.execute("""SELECT tags.id, tags.name, tags.category FROM tags
                           JOIN record_tags ON record_tags.tag_id = tags.id
                           WHERE record_tags.record_id = ? ORDER BY tags.category, tags.name""", (row["id"],)).fetchall()
    result["tags"] = [dict(tag) for tag in tags]
    result["opportunity_score"], result["opportunity_label"] = opportunity(result)
    if compact:
        keep = {"id", "context", "problem", "feeling", "feeling_note", "scene", "occurred_at", "created_at", "status", "tags", *SCORE_FIELDS, "opportunity_score", "opportunity_label"}
        result = {key: value for key, value in result.items() if key in keep}
    return result


def scoring_config():
    config = json.loads((ROOT / "app" / "scoring.json").read_text(encoding="utf-8-sig"))
    weights = config["weights"]
    if set(weights) != set(SCORE_FIELDS) or abs(sum(weights.values()) - 1) > 0.000001:
        raise ValueError("scoring.json 权重必须覆盖五项评分且合计为 1")
    return config


def opportunity(record):
    config = scoring_config()
    if any(record.get(name) is None for name in SCORE_FIELDS):
        return None, "待补评分"
    weighted_mean = sum(record[name] * config["weights"][name] for name in SCORE_FIELDS)
    score = int((weighted_mean - 1) / 4 * 100 + 0.5)
    label = next(band["label"] for band in config["bands"] if score >= band["min"])
    return score, label


def sort_key(sort):
    fields = {"pain": "pain_score", "frequency": "frequency_score", "time": "time_cost_score", "automation": "automation_potential", "opportunity": "opportunity_score"}
    if sort == "oldest":
        return lambda record: (record["occurred_at"], record["id"])
    if sort in fields:
        field = fields[sort]
        return lambda record: (record[field] is not None, record[field] or 0, record["occurred_at"], record["id"])
    return lambda record: (record["occurred_at"], record["id"])


def build_codex_prompt(theme, records):
    now = datetime.now(timezone.utc)
    seven_days = now - timedelta(days=7)
    thirty_days = now - timedelta(days=30)
    def occurred_after(record, threshold):
        return datetime.fromisoformat(record["occurred_at"].replace("Z", "+00:00")) >= threshold
    def unique_text(field, fallback):
        values = []
        for record in records:
            value = record.get(field, "").strip()
            if value and value not in values:
                values.append(value)
        return "\n".join(f"- {value}" for value in values[:5]) or fallback
    scores = [record["opportunity_score"] for record in records if record["opportunity_score"] is not None]
    average_score = round(sum(scores) / len(scores)) if scores else None
    worth = "高" if average_score is not None and average_score >= 80 else "中" if average_score is not None and average_score >= 60 else "低" if average_score is not None else "待补充评分"
    frequencies = [record["repeatability"] for record in records if record.get("repeatability")]
    stats = {
        "last_7_days": sum(occurred_after(record, seven_days) for record in records),
        "last_30_days": sum(occurred_after(record, thirty_days) for record in records),
        "all_time": len(records),
        "opportunity_score": average_score,
        "worth_building": worth,
    }
    description = theme.get("description", "").strip()
    problem_intro = description or "以下记录反映了同一个反复出现的需求。"
    prompt = f"""我要开发一个“{theme['name']}”工具。

目前的问题：

{problem_intro}

相关问题记录：

{unique_text('problem', '尚未归入原始记录。')}

出现次数：

- 最近 7 天：{stats['last_7_days']} 次
- 最近 30 天：{stats['last_30_days']} 次
- 全部时间：{stats['all_time']} 次

目前流程：

{unique_text('current_process', '尚未补充。')}

存在的问题：

{unique_text('pain_point', '尚未补充。')}

当前解决方式及不足：

{unique_text('current_solution', '尚未补充当前解决方式。')}
{unique_text('solution_problem', '尚未补充当前方案的不足。')}

希望实现：

{unique_text('desired_state', '尚未补充理想状态。')}

输入：

{unique_text('input', '尚未明确。')}

处理过程：

根据上述流程和理想状态设计一个低摩擦、可维护的本地工具。

输出：

{unique_text('output', '尚未明确。')}

使用频率：

{', '.join(dict.fromkeys(frequencies)) if frequencies else '尚未判断。'}

项目价值评分：

{str(average_score) + ' / 100' if average_score is not None else '待补充评分'}

是否值得开发：{worth}

请先根据以上真实记录梳理最小可行范围，再分阶段实现；优先降低使用阻力，并确保数据可以完整导出。"""
    return prompt, stats


def make_server(db_path=DEFAULT_DB, port=8765, host="127.0.0.1"):
    initialize(db_path)
    server = ThreadingHTTPServer((host, port), Handler)
    server.db_path = db_path
    return server


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description="Personal needs discovery — local application")
    parser.add_argument("--host", default=configured_host())
    parser.add_argument("--port", type=int, default=configured_port())
    parser.add_argument("--db", default=str(configured_database_path(DEFAULT_DB)))
    args = parser.parse_args()
    server = make_server(args.db, args.port, args.host)
    print(f"Open http://{args.host}:{server.server_port} | SQLite: {args.db}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

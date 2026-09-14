"""SQLite connections and version-one initialization; no third-party dependencies."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "needs.sqlite3"
SCENES = "学习 科研 编程 摄影 生活 文件管理 信息整理 时间管理 AI 社交 其他".split()
PROBLEMS = "重复操作 信息整理 判断困难 容易忘 数据处理 文件处理 搜索 计划 追踪 提醒 自动化 决策".split()


def connect(path=DEFAULT_DB):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def initialize(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript((ROOT / "app" / "schema.sql").read_text(encoding="utf-8-sig"))
        with conn:
            conn.executemany(
                "INSERT OR IGNORE INTO tags(name, category) VALUES (?, ?)",
                [(name, "scene") for name in SCENES] + [(name, "problem") for name in PROBLEMS],
            )
    finally:
        conn.close()

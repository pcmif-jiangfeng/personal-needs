import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from app.db import connect, initialize
from app.server import make_server


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        initialize(self.path)
        self.conn = connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def record(self):
        return self.conn.execute("INSERT INTO records(context,problem,original_context,original_problem) VALUES ('学习','不知道是否掌握','学习','不知道是否掌握')").lastrowid

    def test_reinitialization_preserves_records(self):
        self.record()
        self.conn.commit()
        initialize(self.path)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0], 23)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0], 1)

    def test_minimal_record_and_constraints(self):
        record_id = self.record()
        row = self.conn.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
        self.assertIsNone(row['pain_score'])
        self.assertEqual(row['status'], 'Inbox')
        for sql in ["UPDATE records SET pain_score=6", "UPDATE records SET status='Bad'", "UPDATE records SET context=' '", "UPDATE records SET feeling='{}'", "UPDATE records SET original_problem='changed'", "UPDATE records SET related_need=999"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(sql)

    def test_delete_theme_preserves_record_and_delete_record_removes_links(self):
        record_id = self.record()
        theme_id = self.conn.execute("INSERT INTO themes(name) VALUES ('掌握度')").lastrowid
        self.conn.execute('UPDATE records SET related_need=? WHERE id=?', (theme_id, record_id))
        self.conn.execute('INSERT INTO record_tags VALUES (?, (SELECT MIN(id) FROM tags))', (record_id,))
        self.conn.execute('DELETE FROM themes WHERE id=?', (theme_id,))
        self.assertIsNone(self.conn.execute('SELECT related_need FROM records').fetchone()[0])
        self.conn.execute('DELETE FROM records WHERE id=?', (record_id,))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM record_tags').fetchone()[0], 0)

    def test_http_startup(self):
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base + '/api/health') as response:
                self.assertEqual(json.load(response), {'ok': True, 'phase': 8, 'schema_version': 1, 'records': 0})
            with urlopen(base) as response:
                self.assertIn('个人需求发现', response.read().decode('utf-8-sig'))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_quick_capture_api_preserves_original_expression(self):
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            payload = json.dumps({'context': '  写 Python 作业  ', 'problem': ' 每次都要手动整理文件。 ', 'feeling': ['烦', '重复', '重复', 'not-allowed'], 'feeling_note': '怕漏文件'}, ensure_ascii=False).encode()
            request = Request(f'http://127.0.0.1:{server.server_port}/api/records', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(request) as response:
                self.assertEqual(response.status, 201)
                self.assertEqual(json.load(response)['id'], 1)
            row = self.conn.execute('SELECT * FROM records').fetchone()
            self.assertEqual(row['context'], '写 Python 作业')
            self.assertEqual(row['original_problem'], '每次都要手动整理文件。')
            self.assertEqual(json.loads(row['feeling']), ['烦', '重复'])
            self.assertEqual(row['feeling_note'], '怕漏文件')
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_quick_capture_rejects_missing_required_fields(self):
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            request = Request(f'http://127.0.0.1:{server.server_port}/api/records', data=b'{"context":"","problem":""}', method='POST')
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 422)
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_record_lifecycle_search_and_exports(self):
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            create = Request(base + '/api/records', data=json.dumps({
                'context': '处理摄影素材', 'problem': '挑选重复照片很慢',
                'feeling': ['浪费时间'], 'feeling_note': '容易看漏',
            }, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(create) as response:
                record_id = json.load(response)['id']

            with urlopen(base + '/api/records?q=' + '%E6%91%84%E5%BD%B1') as response:
                listing = json.load(response)
            self.assertEqual(listing['count'], 1)
            self.assertEqual(listing['records'][0]['id'], record_id)

            update_data = {
                'context': '整理摄影素材', 'problem': '大量相似照片难以筛选',
                'feeling': ['浪费时间', '无聊'], 'feeling_note': '容易看漏',
                'current_process': '逐张放大查看', 'pain_point': '无法快速比较',
                'current_solution': '手动加星', 'solution_problem': '仍然很慢',
                'desired_state': '自动归组相似照片', 'input': '照片', 'output': '候选组',
                'repeatability': '每周', 'standardizable': '部分可以',
            }
            update = Request(base + f'/api/records/{record_id}', data=json.dumps(update_data, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='PUT')
            with urlopen(update) as response:
                self.assertEqual(response.status, 200)
            with urlopen(base + f'/api/records/{record_id}') as response:
                item = json.load(response)
            self.assertEqual(item['context'], '整理摄影素材')
            self.assertEqual(item['original_context'], '处理摄影素材')
            self.assertEqual(item['desired_state'], '自动归组相似照片')

            with urlopen(base + '/api/export/json') as response:
                exported = json.load(response)
            self.assertEqual(exported['records'][0]['id'], record_id)
            self.assertIn('themes', exported)
            with urlopen(base + '/api/export/csv') as response:
                csv_text = response.read().decode('utf-8-sig')
            self.assertIn('自动归组相似照片', csv_text)

            delete = Request(base + f'/api/records/{record_id}', method='DELETE')
            with urlopen(delete) as response:
                self.assertEqual(response.status, 204)
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_tags_scores_and_opportunity_sort(self):
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            tag_request = Request(base + '/api/tags', data=json.dumps({'name': '我的流程'}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(tag_request) as response:
                custom_tag = json.load(response)
            self.assertEqual(custom_tag['category'], 'custom')

            for context, problem in [('科研', '格式不一致'), ('学习', '忘记复习')]:
                request = Request(base + '/api/records', data=json.dumps({'context': context, 'problem': problem}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
                with urlopen(request):
                    pass
            payload = {
                'context': '科研', 'problem': '格式不一致', 'scene': '科研', 'feeling': ['重复'],
                'pain_score': 5, 'frequency_score': 4, 'time_cost_score': 3,
                'automation_potential': 5, 'usage_intent': 4, 'tag_ids': [custom_tag['id']],
            }
            update = Request(base + '/api/records/1', data=json.dumps(payload, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='PUT')
            with urlopen(update):
                pass
            with urlopen(base + '/api/records/1') as response:
                item = json.load(response)
            self.assertEqual(item['opportunity_score'], 83)
            self.assertEqual(item['opportunity_label'], '强项目候选')
            self.assertEqual(item['tags'][0]['name'], '我的流程')
            with urlopen(base + '/api/records?sort=opportunity') as response:
                listing = json.load(response)['records']
            self.assertEqual(listing[0]['id'], 1)
            self.assertIsNone(listing[1]['opportunity_score'])
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_analytics_aggregates_distributions_and_rankings(self):
        first = self.conn.execute("""INSERT INTO records
            (context, problem, original_context, original_problem, scene,
             pain_score, frequency_score, time_cost_score, automation_potential, usage_intent)
            VALUES ('整理数据','格式不统一','整理数据','格式不统一','科研',5,4,3,5,4)""").lastrowid
        self.conn.execute("""INSERT INTO records
            (context, problem, original_context, original_problem, scene)
            VALUES ('复习','忘记知识点','复习','忘记知识点','学习')""")
        tag_id = self.conn.execute("SELECT id FROM tags WHERE name='重复操作' AND category='problem'").fetchone()[0]
        self.conn.execute("INSERT INTO record_tags(record_id, tag_id) VALUES (?, ?)", (first, tag_id))
        self.conn.commit()
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/analytics') as response:
                data = json.load(response)
            self.assertEqual(data['summary']['total_records'], 2)
            self.assertEqual(data['summary']['scored_records'], 1)
            self.assertEqual(data['summary']['scoring_completion'], 50)
            self.assertEqual(data['summary']['average_opportunity'], 83)
            self.assertEqual({item['label'] for item in data['scene_counts']}, {'科研', '学习'})
            self.assertEqual(data['problem_tag_counts'], [{'label': '重复操作', 'value': 1}])
            self.assertEqual(data['rankings']['opportunity'][0]['id'], first)
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_theme_creation_assignment_summary_and_safe_delete(self):
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            create_theme = Request(base + '/api/themes', data=json.dumps({
                'name': '学习掌握度', 'description': '追踪掌握与遗忘',
            }, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(create_theme) as response:
                theme_id = json.load(response)['id']
            create_record = Request(base + '/api/records', data=json.dumps({
                'context': '复习物理', 'problem': '不知道是否掌握',
            }, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(create_record) as response:
                record_id = json.load(response)['id']
            update = Request(base + f'/api/records/{record_id}', data=json.dumps({
                'context': '复习物理', 'problem': '不知道是否掌握', 'scene': '学习',
                'pain_score': 4, 'frequency_score': 5, 'time_cost_score': 3,
                'automation_potential': 4, 'usage_intent': 5, 'related_need': theme_id,
            }, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='PUT')
            with urlopen(update):
                pass
            with urlopen(base + '/api/themes') as response:
                data = json.load(response)
            theme = data['themes'][0]
            self.assertEqual(theme['record_count'], 1)
            self.assertEqual(theme['records'][0]['id'], record_id)
            self.assertEqual(theme['average_pain'], 4.0)
            self.assertEqual(theme['average_automation'], 4.0)
            self.assertIsNotNone(theme['first_seen'])
            delete = Request(base + f'/api/themes/{theme_id}', method='DELETE')
            with urlopen(delete) as response:
                self.assertEqual(response.status, 204)
            row = self.conn.execute('SELECT related_need FROM records WHERE id=?', (record_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertIsNone(row['related_need'])
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_weekly_review_excludes_older_records(self):
        now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        old = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        first = self.conn.execute("""INSERT INTO records
            (context, problem, original_context, original_problem, scene, occurred_at,
             pain_score, frequency_score, time_cost_score, automation_potential, usage_intent)
            VALUES ('整理数据','每次改列名','整理数据','每次改列名','科研',?,5,4,3,5,4)""", (now,)).lastrowid
        self.conn.execute("""INSERT INTO records
            (context, problem, original_context, original_problem, scene, occurred_at)
            VALUES ('复习','忘记内容','复习','忘记内容','学习',?)""", (now,))
        self.conn.execute("""INSERT INTO records
            (context, problem, original_context, original_problem, scene, occurred_at)
            VALUES ('旧记录','不应进入本周','旧记录','不应进入本周','生活',?)""", (old,))
        tag_id = self.conn.execute("SELECT id FROM tags WHERE name='重复操作' AND category='problem'").fetchone()[0]
        self.conn.execute("INSERT INTO record_tags(record_id, tag_id) VALUES (?, ?)", (first, tag_id))
        self.conn.commit()
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/review/weekly') as response:
                data = json.load(response)
            self.assertEqual(data['total_records'], 2)
            self.assertEqual({item['label'] for item in data['scene_counts']}, {'科研', '学习'})
            self.assertEqual(data['problem_tag_counts'], [{'label': '重复操作', 'value': 1}])
            self.assertEqual(data['rankings']['pain'][0]['id'], first)
            self.assertEqual(data['rankings']['opportunity'][0]['opportunity_score'], 83)
            self.assertLessEqual(data['week']['start'], data['week']['end'])
        finally:
            server.shutdown(); server.server_close(); worker.join()

    def test_codex_prompt_generation_and_download(self):
        theme_id = self.conn.execute("INSERT INTO themes(name, description) VALUES ('实验数据整理', '减少重复的数据清洗工作')").lastrowid
        self.conn.execute("""INSERT INTO records
            (context, problem, original_context, original_problem, scene, related_need,
             current_process, pain_point, current_solution, solution_problem, desired_state,
             input, output, repeatability, pain_score, frequency_score, time_cost_score,
             automation_potential, usage_intent)
            VALUES ('处理实验','列名每次都不同','处理实验','列名每次都不同','科研',?,
                    '读取 CSV 后手动改列名','容易漏列','临时改 Python 代码','下次仍要重做',
                    '拖入文件后自动统一格式','CSV 文件','清洗后的文件和图表','每周',5,5,4,5,5)""", (theme_id,))
        self.conn.commit()
        server = make_server(self.path, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + f'/api/themes/{theme_id}/prompt') as response:
                data = json.load(response)
            self.assertIn('我要开发一个“实验数据整理”工具', data['prompt'])
            self.assertIn('读取 CSV 后手动改列名', data['prompt'])
            self.assertIn('拖入文件后自动统一格式', data['prompt'])
            self.assertEqual(data['stats']['all_time'], 1)
            self.assertEqual(data['stats']['last_30_days'], 1)
            self.assertGreaterEqual(data['stats']['opportunity_score'], 80)
            with urlopen(base + f'/api/themes/{theme_id}/prompt?download=1') as response:
                text = response.read().decode('utf-8')
                disposition = response.headers['Content-Disposition']
            self.assertIn('是否值得开发：高', text)
            self.assertIn('attachment', disposition)
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__':
    unittest.main()

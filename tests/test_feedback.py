import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import core
from app.main import app


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = core.DB_PATH
        core.DB_PATH = Path(self.temp.name) / 'feedback.sqlite3'
        core.init_db()
        core.add_product('demo_box', '演示盒')
        core.add_document('demo_box', '1.0', '说明', '说明', 'demo.md',
                          '演示盒支持创建文字记录。'.encode())
        self.client = TestClient(app)

    def tearDown(self):
        core.DB_PATH = self.previous_db
        self.temp.cleanup()

    def test_rating_is_bound_to_answer_and_visible_in_stats(self):
        first = self.client.post('/api/ask', json={
            'question': '演示盒支持创建文字记录吗？', 'product_id': 'demo_box', 'version': '1.0'}).json()
        self.assertEqual(first['status'], 'answered')
        second = self.client.post('/api/ask', json={
            'question': '演示盒支持创建文字记录吗？', 'product_id': 'demo_box',
            'version': '1.0', 'session_id': first['session_id']}).json()
        payload = {'session_id': first['session_id'], 'message_id': first['message_id'], 'rating': 1}
        self.assertEqual(self.client.post('/api/feedback', json=payload).status_code, 200)
        self.assertEqual(self.client.get('/api/stats').json()['feedback_positive'], 1)
        payload['rating'] = -1
        self.assertEqual(self.client.post('/api/feedback', json=payload).status_code, 200)
        stats = self.client.get('/api/stats').json()
        self.assertEqual((stats['feedback_positive'], stats['feedback_negative']), (0, 1))
        self.assertEqual(self.client.post('/api/feedback', json={
            'session_id': second['session_id'], 'message_id': second['message_id'], 'rating': 1
        }).status_code, 200)
        self.assertEqual(self.client.get('/api/stats').json()['feedback_positive'], 1)
        with core.connect() as db:
            rows = db.execute('SELECT message_id,rating FROM feedback ORDER BY message_id').fetchall()
        self.assertEqual([(r['message_id'], r['rating']) for r in rows],
                         [(first['message_id'], -1), (second['message_id'], 1)])

    def test_rejects_wrong_session_or_unanswered_message(self):
        answered = self.client.post('/api/ask', json={
            'question': '演示盒支持创建文字记录吗？', 'product_id': 'demo_box', 'version': '1.0'}).json()
        missing = self.client.post('/api/ask', json={
            'question': '演示盒支持语音转写吗？', 'product_id': 'demo_box', 'version': '1.0'}).json()
        self.assertEqual(missing['status'], 'no_answer')
        for session_id, message_id, rating, expected in [
            ('wrong-session', answered['message_id'], 1, 404),
            (missing['session_id'], missing['message_id'], -1, 404),
            (answered['session_id'], answered['message_id'], 0, 400),
        ]:
            response = self.client.post('/api/feedback', json={
                'session_id': session_id, 'message_id': message_id, 'rating': rating})
            self.assertEqual(response.status_code, expected, response.text)

    def test_existing_feedback_table_gets_message_column(self):
        with core.connect() as db:
            db.execute('DROP TABLE feedback')
            db.execute('''CREATE TABLE feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,
                          session_id TEXT NOT NULL, rating INTEGER NOT NULL,
                          note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)''')
            db.execute("INSERT INTO feedback(session_id,rating,note,created_at) VALUES('old',1,'','today')")
        core.init_db()
        with core.connect() as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(feedback)')}
            old = db.execute('SELECT message_id,rating FROM feedback').fetchone()
        self.assertIn('message_id', columns)
        self.assertIsNone(old['message_id'])
        self.assertEqual(old['rating'], 1)


if __name__ == '__main__':
    unittest.main()

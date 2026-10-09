import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import core
from app.main import app


class DocumentReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = core.DB_PATH
        core.DB_PATH = Path(self.temp.name) / 'review.sqlite3'
        core.init_db()
        core.add_product('review', '测试产品')
        self.client = TestClient(app)
        self.content = ('# 参数\n第 1 页\nQ: 附件限制是多少？\nA: 附件上限：25 MB\n'
                        'Q: 支持什么格式？\nA: 支持 PDF 导出\n支持 PDF 导出').encode()
        self.data = {'product_id': 'review', 'version': '2.0', 'max_chars': '120',
                     'overlap': '20', 'remove_page_markers': 'true',
                     'remove_duplicates': 'true'}

    def tearDown(self):
        core.DB_PATH = self.previous_db
        self.temp.cleanup()

    def request(self, path, **extra):
        return self.client.post(path, data={**self.data, **extra},
                                files={'file': ('params.md', self.content, 'text/markdown')})

    def test_preview_is_read_only_and_review_indexes_original_answer(self):
        response = self.request('/api/documents/preview')
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertNotIn('第 1 页', preview['text'])
        self.assertEqual(preview['cleaning']['settings']['max_chars'], 120)
        self.assertTrue(all(len(c) <= 120 for c in preview['chunks']))
        with core.connect() as db:
            for table in ('documents', 'document_texts', 'chunks', 'faqs'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)
        index = next(i for i, f in enumerate(preview['faqs']) if '25 MB' in f['answer'])
        saved = self.request('/api/documents', review='true', selected_faqs=json.dumps([
            {'index': index, 'question': '附件最多可以上传多少 MB？', 'answer': '假的 999 MB'}]))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['faqs'], 1)
        faqs = self.client.get('/api/faqs', params={'product_id': 'review', 'version': '2.0'}).json()
        self.assertEqual(faqs[0]['question'], '附件最多可以上传多少 MB？')
        self.assertEqual(faqs[0]['answer'], preview['faqs'][index]['answer'])
        self.assertEqual(self.client.get('/api/faqs', params={'product_id': 'review', 'version': '1.0'}).json(), [])
        answer = core.ask('附件最多可以上传多少 MB？', product_id='review', version='2.0')
        self.assertEqual(answer['status'], 'answered')
        self.assertIn('25 MB', answer['answer'])

    def test_invalid_selection_and_settings_do_not_write(self):
        for selection in ([{'index': 999, 'question': '问题'}],
                          [{'index': 0, 'question': ' '}],
                          [{'index': 0, 'question': '问题'}] * 2, {'index': 0}):
            response = self.request('/api/documents', review='true', selected_faqs=json.dumps(selection))
            self.assertEqual(response.status_code, 400, response.text)
        for settings in ({'max_chars': '119'}, {'overlap': '60'}, {'version': ' '}):
            self.assertEqual(self.request('/api/documents/preview', **settings).status_code, 400)
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0], 0)

    def test_cleaning_switches_and_zero_selected_qa(self):
        preview = self.request('/api/documents/preview', remove_page_markers='false',
                               remove_duplicates='false').json()
        self.assertIn('第 1 页', preview['text'])
        self.assertEqual(preview['cleaning']['page_markers_removed'], 0)
        self.assertEqual(preview['cleaning']['adjacent_duplicates_removed'], 0)
        saved = self.request('/api/documents', review='true', selected_faqs='[]')
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['faqs'], 0)
        self.assertGreater(saved.json()['chunks'], 0)

    def test_no_qa_still_produces_chunks_and_long_heading_respects_limit(self):
        self.content = ('# ' + '说明' * 40 + '\n' + '产品采用蓝色外壳。' * 60).encode()
        preview = self.request('/api/documents/preview').json()
        self.assertEqual(preview['faqs'], [])
        self.assertTrue(preview['chunks'])
        self.assertTrue(all(len(c) <= 120 for c in preview['chunks']))
        self.content = b'\nPage 1 of 1\n'
        self.assertEqual(self.request('/api/documents/preview').status_code, 400)


if __name__ == '__main__':
    unittest.main()

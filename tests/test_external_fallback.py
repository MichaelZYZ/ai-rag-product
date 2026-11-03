import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import core, llm_config
from app.main import app


class ExternalFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(core, 'DB_PATH', Path(self.temp.name) / 'fallback.sqlite3')
        self.db.start()
        self.env = patch.dict(os.environ, {'RAG_RETRIEVER': 'hash', 'RAG_ANSWER_MODE': 'auto',
            'RAG_EXTERNAL_FALLBACK': '1', 'RAG_LLM_DISABLED': '0',
            'LLM_BASE_URL': '', 'LLM_API_KEY': '', 'LLM_MODEL': ''})
        self.env.start()
        core.init_db()
        core.add_product('nova_notes', '星云笔记')
        core.add_document('nova_notes', '2.0', '说明', '说明', 'manual.md',
                          '星云笔记 2.0 的附件上传限制为单个文件 25 MB。'.encode())
        llm_config.save(core.DB_PATH, 'openrouter', api_key='test-secret', answer_mode='auto')
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.db.stop()
        self.temp.cleanup()

    def ask(self, question='是否支持语音转写？', scoped=True):
        body = {'question': question}
        if scoped:
            body.update(product_id='nova_notes', version='2.0')
        response = self.client.post('/api/ask', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('test-secret', response.text)
        return response.json()

    @staticmethod
    def response(text='这是通用知识参考，请核对具体产品。', model='vendor/free-model-v1'):
        data = {'choices': [{'message': {'content': text}}]}
        if model is not None:
            data['model'] = model
        return io.BytesIO(json.dumps(data).encode())

    def test_external_source_model_persistence_stats_feedback_and_gap(self):
        captured = {}
        def respond(request, timeout):
            captured['request'] = json.loads(request.data)
            return self.response()
        with core.connect() as db:
            count = db.execute('SELECT count(*) FROM faqs').fetchone()[0]
        with patch('urllib.request.urlopen', side_effect=respond):
            result = self.ask()
        self.assertEqual(result['status'], 'external_answer')
        self.assertEqual(result['generation_mode'], 'llm_external')
        self.assertEqual(result['answer_source']['type'], 'external_model')
        self.assertIn('未经产品资料验证', result['answer_source']['label'])
        self.assertEqual(result['model_info']['requested_model'], 'openrouter/free')
        self.assertEqual(result['model_info']['actual_model'], 'vendor/free-model-v1')
        self.assertEqual(result['sources'], [])
        self.assertIsNone(result['confidence'])
        self.assertEqual(result['display_answer'], result['answer'])
        self.assertNotIn('我查到', result['display_answer'])
        self.assertIsNotNone(result['knowledge_gap'])
        self.assertNotIn('25 MB', captured['request']['messages'][1]['content'])
        self.assertIn('没有进行联网搜索', captured['request']['messages'][0]['content'])
        with core.connect() as db:
            provenance = dict(db.execute('SELECT * FROM answer_provenance WHERE message_id=?',
                                        (result['message_id'],)).fetchone())
            self.assertEqual(provenance['source_type'], 'external_model')
            self.assertEqual(provenance['actual_model'], 'vendor/free-model-v1')
            self.assertEqual(db.execute('SELECT count(*) FROM faqs').fetchone()[0], count)
        stats = self.client.get('/api/stats').json()
        self.assertEqual(stats['external_answers'], 1)
        self.assertEqual(stats['answered'], 0)
        self.assertEqual(stats['resolution_rate'], 0)
        self.assertEqual(stats['open_gap_count'], 1)
        rating = self.client.post('/api/feedback', json={'message_id': result['message_id'],
                        'session_id': result['session_id'], 'rating': 1})
        self.assertEqual(rating.status_code, 200)

    def test_known_faq_keeps_document_source_without_model_call(self):
        with patch('urllib.request.urlopen') as remote:
            result = self.ask('附件大小限制是多少？')
            remote.assert_not_called()
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer_source']['type'], 'knowledge_base')
        self.assertEqual(result['sources'][0]['source'], 'manual.md')
        self.assertIsNone(result['model_info'])

    def test_opt_out_extractive_and_offline_evaluation_never_send_requests(self):
        scenarios = [({'answer_mode': 'auto', 'fallback_enabled': False}, {}),
                     ({'answer_mode': 'extractive'}, {}),
                     ({'answer_mode': 'auto'}, {'RAG_LLM_DISABLED': '1'}),
                     ({'answer_mode': 'auto'}, {'RAG_EXTERNAL_FALLBACK': '0'})]
        for config, environment in scenarios:
            llm_config.save(core.DB_PATH, 'openrouter', api_key='test-secret', **config)
            with patch.dict(os.environ, environment), patch('urllib.request.urlopen') as remote:
                result = self.ask()
                remote.assert_not_called()
            self.assertEqual(result['status'], 'no_answer')

    def test_provider_failure_keeps_error_and_requested_model_without_fake_actual_model(self):
        error = urllib.error.HTTPError('https://example.test', 429, 'private-error-test-secret', {}, None)
        with patch('urllib.request.urlopen', side_effect=error):
            result = self.ask()
        self.assertEqual(result['generation_mode'], 'error')
        self.assertEqual(result['generation_error'], 'HTTP429')
        self.assertIn('额度', result['display_answer'])
        self.assertEqual(result['answer_source']['type'], 'system')
        self.assertIsNone(result['model_info']['actual_model'])
        self.assertIsNotNone(result['knowledge_gap'])

    def test_grounded_model_refusal_triggers_general_fallback_with_final_actual_model(self):
        evidence = [{'chunk_id': 'fixture', 'source': 'manual.md', 'category': '说明',
                     'text': '附件上限为 25 MB。', 'score': 0.9}]
        payloads = []
        def respond(request, timeout):
            payloads.append(json.loads(request.data))
            return (self.response(core.INSUFFICIENT_KNOWLEDGE, 'grounded-v1') if len(payloads) == 1
                    else self.response('这是一条通用建议。', 'general-v2'))
        with patch.object(core, 'retrieve', return_value=evidence), patch.object(core, 'match_faq', return_value=None), \
                patch('urllib.request.urlopen', side_effect=respond):
            result = self.ask()
        self.assertEqual(len(payloads), 2)
        self.assertIn('资料：', payloads[0]['messages'][1]['content'])
        self.assertNotIn('资料：', payloads[1]['messages'][1]['content'])
        self.assertEqual(result['model_info']['actual_model'], 'general-v2')
        self.assertEqual(result['status'], 'external_answer')
        self.assertEqual(result['sources'], [])

    def test_missing_actual_model_is_reported_as_unknown(self):
        with patch('urllib.request.urlopen', return_value=self.response(model=None)):
            result = self.ask()
        self.assertEqual(result['model_info']['requested_model'], 'openrouter/free')
        self.assertIsNone(result['model_info']['actual_model'])
        self.assertIn('服务未返回实际模型标识', self.client.get('/').text)

    def test_general_unknown_question_can_use_model_but_catalog_and_handoff_stay_local(self):
        with patch('urllib.request.urlopen', side_effect=lambda *a, **k: self.response()):
            result = self.ask('什么是量子纠缠？', scoped=False)
        self.assertEqual(result['status'], 'external_answer')
        with patch('urllib.request.urlopen') as remote:
            handoff = self.ask('我要退款')
            catalog = self.ask('有没有火星商城的知识库？', scoped=False)
            remote.assert_not_called()
        self.assertEqual(handoff['status'], 'handoff')
        self.assertEqual(catalog['status'], 'no_product')


if __name__ == '__main__':
    unittest.main()

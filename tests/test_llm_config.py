import io
import json
import os
import tempfile
import unittest
import urllib.error
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import core, llm_config
from app.main import app
from scripts import package_project
from zipfile import ZipFile


class LLMConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(core, 'DB_PATH', Path(self.temp.name) / 'db.sqlite3')
        self.db.start()
        self.env = patch.dict(os.environ, {'LLM_BASE_URL': '', 'LLM_API_KEY': '', 'LLM_MODEL': '',
                                          'RAG_LLM_DISABLED': '0', 'RAG_ANSWER_MODE': 'auto'})
        self.env.start()
        core.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.db.stop()
        self.temp.cleanup()

    def save(self, **overrides):
        body = {'provider_id': 'openrouter', 'model': 'openrouter/free', 'api_key': 'secret-openrouter', 'answer_mode': 'llm'}
        body.update(overrides)
        result = self.client.put('/api/llm/config', json=body)
        self.assertEqual(result.status_code, 200, result.text)
        return result

    def test_default_save_reload_redaction_and_reset(self):
        initial = self.client.get('/api/llm/config').json()
        self.assertEqual(initial['provider_id'], 'openrouter')
        self.assertEqual(initial['model'], 'openrouter/free')
        self.assertFalse(initial['configured'])
        self.assertEqual(self.client.post('/api/llm/test').status_code, 400)
        saved = self.save()
        self.assertTrue(saved.json()['has_api_key'])
        self.assertNotIn('secret-openrouter', saved.text)
        public = self.client.get('/api/llm/config')
        self.assertNotIn('secret-openrouter', public.text)
        self.assertTrue(core.answer_prompt_config()['model_enabled'])
        self.assertEqual(self.client.get('/api/rag/status').json()['answer_mode'], 'llm')
        with core.connect() as db:
            self.assertNotIn('secret-openrouter', '\n'.join(db.iterdump()))
        if os.name != 'nt':
            self.assertEqual(llm_config.config_path(core.DB_PATH).stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.client.delete('/api/llm/config').json()['configured'])
        self.assertFalse(llm_config.config_path(core.DB_PATH).exists())

    def test_provider_switch_and_custom_destination_do_not_reuse_other_keys(self):
        self.save()
        switched = self.save(provider_id='groq', model='openai/gpt-oss-20b', api_key=None)
        self.assertFalse(switched.json()['configured'])
        self.assertEqual(llm_config.effective(core.DB_PATH)['api_key'], '')
        back = self.save(api_key=None)
        self.assertTrue(back.json()['configured'])
        self.save(provider_id='custom', base_url='http://127.0.0.1:11434/v1', model='local-model', api_key='local-key')
        changed = self.save(provider_id='custom', base_url='https://another.example/v1', model='model', api_key=None)
        self.assertFalse(changed.json()['configured'])

    def test_live_request_uses_saved_provider_model_and_prompt(self):
        self.save(provider_id='gemini', model='gemini-3.8-flash', api_key='secret-gemini')
        captured = {}
        def respond(request, timeout):
            captured['url'] = request.full_url
            captured['body'] = json.loads(request.data)
            captured['authorization'] = request.get_header('Authorization')
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': '依据资料回答。[1]'}}]}).encode())
        with patch('urllib.request.urlopen', side_effect=respond):
            answer = core.llm_answer('问题', [{'text': '来源事实'}])
        self.assertIn('依据资料', answer)
        self.assertEqual(captured['url'], 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions')
        self.assertEqual(captured['authorization'], 'Bearer secret-gemini')
        self.assertEqual(captured['body']['model'], 'gemini-3.8-flash')
        self.assertIn('来源事实', captured['body']['messages'][1]['content'])

    def test_connection_test_payload_errors_and_response_redaction(self):
        self.save()
        seen = {}
        def respond(request, timeout):
            seen['body'] = json.loads(request.data)
            return io.BytesIO(json.dumps({'model': 'actual-free-model', 'choices': [{'message': {'content': 'OK'}}]}).encode())
        with patch('urllib.request.urlopen', side_effect=respond):
            result = self.client.post('/api/llm/test')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['model'], 'actual-free-model')
        self.assertEqual(seen['body']['messages'], [{'role': 'user', 'content': '请仅回复 OK。'}])
        error = urllib.error.HTTPError('https://example.test', 429, 'secret-provider-error', {}, None)
        with patch('urllib.request.urlopen', side_effect=error):
            failure = self.client.post('/api/llm/test')
        self.assertEqual(failure.status_code, 503)
        self.assertIn('额度', failure.json()['detail'])
        self.assertNotIn('secret-provider-error', failure.text)

    def test_invalid_configuration_does_not_replace_valid_file_and_disable_flag(self):
        self.save()
        path = llm_config.config_path(core.DB_PATH)
        original = path.read_bytes()
        for body in [dict(provider_id='unknown'), dict(provider_id='groq', model='paid-model'),
                     dict(provider_id='custom', model='x', base_url='http://remote.example/v1'),
                     dict(provider_id='custom', model='x', base_url='https://user:key@example.test/v1')]:
            self.assertEqual(self.client.put('/api/llm/config', json=body).status_code, 400)
            self.assertEqual(path.read_bytes(), original)
        with patch.dict(os.environ, {'RAG_LLM_DISABLED': '1'}), patch('urllib.request.urlopen') as remote:
            self.assertIsNone(core.llm_answer('测试', [{'text': '资料'}]))
            remote.assert_not_called()

    def test_environment_requires_complete_explicit_configuration(self):
        with patch.dict(os.environ, {'LLM_BASE_URL': 'https://example.test/v1', 'LLM_API_KEY': 'test-key', 'LLM_MODEL': ''}):
            self.assertFalse(llm_config.enabled(core.DB_PATH))
        with patch.dict(os.environ, {'LLM_BASE_URL': 'https://example.test/v1', 'LLM_API_KEY': 'test-key', 'LLM_MODEL': 'model'}):
            self.assertTrue(llm_config.enabled(core.DB_PATH))
            self.assertEqual(llm_config.public_config(core.DB_PATH)['source'], 'environment')

    def test_submission_archive_excludes_credentials(self):
        root = Path(self.temp.name) / 'package'
        (root / 'data').mkdir(parents=True)
        (root / 'data/knowledge.json').write_text('[]')
        (root / 'data/rag.llm.json').write_text('{"api_key":"never-package"}')
        (root / '.env').write_text('LLM_API_KEY=never-package')
        (root / '.env.example').write_text('LLM_API_KEY=')
        (root / '.gitignore').write_text('*.llm.json')
        with patch.object(package_project, 'ROOT', root):
            package_project.main()
        with ZipFile(root / 'dist/rag_course_project.zip') as archive:
            self.assertIn('data/knowledge.json', archive.namelist())
            self.assertNotIn('data/rag.llm.json', archive.namelist())
            self.assertNotIn('.env', archive.namelist())
            self.assertNotIn(b'never-package', b''.join(archive.read(n) for n in archive.namelist()))

    def test_benchmark_uses_saved_provider_without_exporting_key(self):
        import benchmark
        self.save()
        output = Path(self.temp.name) / 'benchmark'
        def respond(request, timeout):
            self.assertEqual(request.get_header('Authorization'), 'Bearer secret-openrouter')
            self.assertEqual(json.loads(request.data)['model'], 'openrouter/free')
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': '受控测试回答。[1]'}}]}).encode())
        with patch.object(sys, 'argv', ['benchmark.py', '--retrievers', 'hash', '--with-llm', '--output', str(output)]), \
                patch('urllib.request.urlopen', side_effect=respond):
            benchmark.main()
        report = json.loads((output / 'benchmark.json').read_text())
        self.assertEqual(report['llm_model'], 'openrouter/free')
        self.assertGreater(report['runs']['hash_llm']['llm_answers'], 0)
        for path in output.iterdir():
            self.assertNotIn('secret-openrouter', path.read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()

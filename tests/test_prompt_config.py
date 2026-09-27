import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import core
from app.main import app


class PromptConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = core.DB_PATH
        core.DB_PATH = Path(self.temp.name) / 'prompt.sqlite3'
        core.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        core.DB_PATH = self.previous_db
        self.temp.cleanup()

    def test_default_save_reload_and_reset(self):
        default = core.default_answer_prompt()
        initial = self.client.get('/api/prompt')
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()['prompt'], default)
        self.assertEqual(initial.json()['source'], 'default')

        saved = self.client.put('/api/prompt', json={'prompt': '  只根据资料回答，并使用简洁友好的中文。  '})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['source'], 'custom')
        self.assertEqual(saved.json()['prompt'], '只根据资料回答，并使用简洁友好的中文。')
        self.assertEqual(self.client.get('/api/prompt').json()['prompt'], saved.json()['prompt'])
        self.assertEqual(self.client.put('/api/prompt', json={'prompt': '短'}).status_code, 400)
        self.assertEqual(self.client.get('/api/prompt').json()['prompt'], saved.json()['prompt'])

        restored = self.client.delete('/api/prompt')
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()['source'], 'default')
        self.assertEqual(restored.json()['prompt'], default)

    def test_llm_request_uses_saved_prompt_without_restart(self):
        custom = '你是产品顾问，只按提供的资料回答。'
        self.client.put('/api/prompt', json={'prompt': custom})
        captured = {}

        def fake_urlopen(request, timeout):
            captured['payload'] = json.loads(request.data)
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': '已回答。'}}]}).encode())

        with patch.dict('os.environ', {'LLM_BASE_URL': 'https://example.test/v1',
                                       'LLM_API_KEY': 'test-key', 'LLM_MODEL': 'test-model'}):
            with patch('urllib.request.urlopen', side_effect=fake_urlopen):
                response = core.llm_answer('如何使用？', [{'text': '资料原句。'}])
        self.assertEqual(response, '已回答。')
        self.assertEqual(captured['payload']['messages'][0]['content'], custom)
        self.assertIn('资料原句。', captured['payload']['messages'][1]['content'])


if __name__ == '__main__':
    unittest.main()

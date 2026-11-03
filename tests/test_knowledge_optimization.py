import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import core
from app.cleaning import clean_document
from app.faq import extract_faqs, extract_training_faqs
from app.main import app


MARKDOWN = '''---
title: 雾灯相机说明
---
# **产品介绍**
雾灯相机是一款用于拍摄与资料管理的设备。

## 数据备份
- 支持本地备份，不支持云端同步。
> [帮助中心](https://example.test/help)
---
## 账户管理
- **Q：如何重置密码？**
- **A：** 在登录页点击“找回密码”，使用注册邮箱重置。
---
## 产品参数
| 参数 | 说明 |
| --- | --- |
| 附件上限 | **25 MB** |
| 工作温度 | -5°C 至 +40°C |
| 保修期 | 12 个月 |
| 颜色 | 蓝 |
```bash
backup --path data_file --limit 25
```
'''


class KnowledgeOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(core, 'DB_PATH', Path(self.temp.name) / 'knowledge.sqlite3')
        self.db.start()
        self.env = patch.dict(os.environ, {'RAG_RETRIEVER': 'hash', 'RAG_ANSWER_MODE': 'auto',
                                          'LLM_BASE_URL': '', 'LLM_API_KEY': '', 'LLM_MODEL': ''})
        self.env.start()
        core.init_db()
        core.add_product('mist_camera', '雾灯相机')
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.db.stop()
        self.temp.cleanup()

    def preview(self):
        response = self.client.post('/api/documents/preview', data={'product_id': 'mist_camera', 'version': '2.0'},
                                   files={'file': ('guide.md', MARKDOWN.encode(), 'text/markdown')})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def import_reviewed(self):
        preview = self.preview()
        selection = [{'index': i, 'question': f['question']} for i, f in enumerate(preview['faqs'])]
        response = self.client.post('/api/documents', data={'product_id': 'mist_camera', 'version': '2.0',
            'review': 'true', 'selected_faqs': json.dumps(selection)},
            files={'file': ('guide.md', MARKDOWN.encode(), 'text/markdown')})
        self.assertEqual(response.status_code, 200, response.text)
        return preview

    def ask(self, question, version='2.0'):
        response = self.client.post('/api/ask', json={'question': question, 'product_id': 'mist_camera', 'version': version})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_markdown_cleaning_retains_facts_tables_questions_and_code(self):
        preview = self.preview()
        text = preview['text']
        for noise in ['**', '```', '| ---', '> ', '- **']:
            self.assertNotIn(noise, text)
        for fact in ['附件上限: 25 MB', '工作温度: -5°C 至 +40°C', '不支持云端同步',
                     'data_file --limit 25', 'A: 在登录页', '# 产品介绍']:
            self.assertIn(fact, text)
        self.assertEqual(preview['cleaning']['table_rows_converted'], 4)
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0], 0)

    def test_references_are_not_answers_and_alternate_questions_use_evidence(self):
        preview = self.import_reviewed()
        self.assertTrue(any(f['related_questions'] for f in preview['faqs']))
        self.assertTrue(any('数据备份' in f['question'] for f in preview['faqs']))
        reset = self.ask('密码忘了怎么办？')
        self.assertEqual(reset['status'], 'answered')
        self.assertIn('注册邮箱', reset['answer'])
        maximum = self.ask('附件上限是多少？')
        self.assertEqual(maximum['status'], 'answered')
        self.assertIn('25 MB', maximum['answer'])
        alternate = self.ask('文件大小上限是多少？')
        self.assertEqual(alternate['status'], 'answered')
        self.assertIn('25 MB', alternate['answer'])
        negative = self.ask('是否支持云端同步？')
        self.assertEqual(negative['status'], 'answered')
        self.assertIn('不支持云端同步', negative['answer'])
        self.assertNotEqual(self.ask('密码忘了怎么办？', version='1.0')['status'], 'answered')
        self.assertFalse(extract_training_faqs('帮助中心 (https://example.test/help)', '雾灯相机'))

    def test_gap_button_payload_manual_supplement_and_immediate_reask(self):
        self.import_reviewed()
        first = self.ask('是否支持语音转写？')
        self.assertEqual(first['status'], 'no_answer')
        self.assertEqual(first['answer'], core.INSUFFICIENT_KNOWLEDGE)
        self.assertEqual(first['display_answer'], first['answer'])
        gap = first['knowledge_gap']
        self.assertEqual(gap['question'], '是否支持语音转写？')
        self.assertEqual((gap['product_id'], gap['version']), ('mist_camera', '2.0'))
        saved = self.client.post('/api/gaps/%s/answer' % gap['id'], json={
            'product_id': gap['product_id'], 'version': gap['version'], 'question': gap['question'],
            'answer': '雾灯相机 2.0 不支持语音转写。'})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['resolved_count'], 1)
        answered = self.ask(gap['question'])
        self.assertEqual(answered['status'], 'answered')
        self.assertEqual(answered['sources'][0]['source'], '人工补充')
        self.assertIsNone(answered['knowledge_gap'])
        page = self.client.get('/').text
        self.assertIn('手动补充这个问题', page)
        self.assertIn('关联问法', page)

    def test_model_error_does_not_create_false_knowledge_gap(self):
        self.import_reviewed()
        with patch.dict(os.environ, {'RAG_ANSWER_MODE': 'llm'}), patch.object(core, 'llm_answer', side_effect=TimeoutError):
            result = self.ask('附件上限是多少？')
        self.assertEqual(result['generation_mode'], 'error')
        self.assertIsNone(result['knowledge_gap'])
        self.assertNotIn('资料储备不够', result['display_answer'])
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM unanswered').fetchone()[0], 0)

    def test_cleanup_preserves_math_identifiers_and_obsolete_meaning(self):
        source = '# 参数\n阈值: -5°C\n公式: 2 * 3 = 6\n变量: `data_file`\n~~旧上限 10 MB~~ 新上限 25 MB'
        text, _ = clean_document(source, source_format='.md')
        self.assertIn('-5°C', text)
        self.assertIn('2 * 3 = 6', text)
        self.assertIn('data_file', text)
        self.assertIn('(已删除: 旧上限 10 MB)', text)
        self.assertFalse(any('旧上限' in f['answer'] for f in extract_training_faqs(text, '测试产品')))
        tasks, _ = clean_document('- [x] 本地备份\n- [ ] 云端同步', source_format='.md')
        self.assertIn('已勾选: 本地备份', tasks)
        self.assertIn('未勾选: 云端同步', tasks)


if __name__ == '__main__':
    unittest.main()

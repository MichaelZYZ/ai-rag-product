import tempfile
import unittest
from pathlib import Path

from app import core


class ConversationalAnswerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = core.DB_PATH
        core.DB_PATH = Path(self.temp.name) / 'conversation.sqlite3'
        core.init_db()
        core.add_product('cloud_box', '云盒')
        core.add_document('cloud_box', '2.0', '说明', '帮助', 'help.md',
                          ('# 常见问题\nQ: 云盒如何重置密码？\n'
                           'A: 在登录页点击找回密码，然后使用注册邮箱重置。\n'
                           '云盒 2.0 的附件上传限制为单个文件 25 MB。').encode())

    def tearDown(self):
        core.DB_PATH = self.previous_db
        self.temp.cleanup()

    def test_display_answer_is_warmer_but_keeps_factual_answer_and_source(self):
        result = core.ask('云盒如何重置密码？', product_id='cloud_box', version='2.0')
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer'], '在登录页点击找回密码,然后使用注册邮箱重置。')
        self.assertIn(result['answer'], result['display_answer'])
        self.assertNotEqual(result['answer'], result['display_answer'])
        self.assertEqual(result['sources'][0]['source'], 'help.md')
        self.assertTrue(any('上传' in q for q in result['suggested_questions']))
        self.assertFalse(any('重置密码' in q for q in result['suggested_questions']))

    def test_missing_fact_explains_scope_without_inventing_answer(self):
        result = core.ask('云盒支持语音转写吗？', product_id='cloud_box', version='2.0')
        self.assertEqual(result['status'], 'no_answer')
        self.assertIn('云盒 2.0', result['display_answer'])
        self.assertIn('没在', result['display_answer'])
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['suggested_questions'], [])


if __name__ == '__main__':
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import core, introduction


class ProductIntroductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(core, 'DB_PATH', Path(self.temp.name) / 'intro.sqlite3')
        self.db.start()
        self.env = patch.dict(os.environ, {'RAG_RETRIEVER': 'hash', 'RAG_ANSWER_MODE': 'auto',
                                          'LLM_BASE_URL': '', 'LLM_API_KEY': '', 'LLM_MODEL': ''})
        self.env.start()
        core.init_db()
        core.add_product('nova_notes', '星云笔记', ['笔记'])
        core.add_document('nova_notes', '2.0', '说明', '说明', 'v2.md',
                          '星云笔记 2.0 支持创建文字笔记和标签。\n星云笔记 2.0 附件上限为 25 MB。'.encode())
        core.add_document('nova_notes', '1.0', '说明', '说明', 'v1.md',
                          '星云笔记是一款离线笔记工具。'.encode())

    def tearDown(self):
        self.env.stop()
        self.db.stop()
        self.temp.cleanup()

    def test_intro_paraphrases_and_unique_short_name_resolve_without_api(self):
        for question in ['什么是星云', '什么是星云笔记', '星云是什么', '星云笔记是什么', '介绍一下星云笔记']:
            result = core.ask(question, product_id='nova_notes', version='2.0')
            self.assertEqual(result['status'], 'answered', question)
            self.assertIn('支持创建文字笔记和标签', result['answer'])
            self.assertEqual(result['evidence_match'], 'product_introduction')
            self.assertEqual(result['sources'][0]['source'], 'v2.md')
        inferred = core.ask('什么是星云')
        self.assertEqual(inferred['product_id'], 'nova_notes')
        self.assertEqual(inferred['status'], 'answered')

    def test_existing_manual_concept_answer_is_used_and_version_isolated(self):
        core.supplement_gap(None, 'nova_notes', '2.0', '概念', '星云笔记的核心是帮助整理资料和创作。')
        current = core.ask('什么是星云', product_id='nova_notes', version='2.0')
        self.assertIn('整理资料和创作', current['answer'])
        self.assertEqual(current['generation_mode'], 'faq')
        old = core.ask('什么是星云', product_id='nova_notes', version='1.0')
        self.assertIn('离线笔记工具', old['answer'])
        self.assertNotIn('整理资料和创作', old['answer'])

    def test_unknown_fact_or_definition_is_not_replaced_with_generic_intro(self):
        for question in ['什么是星云的退款政策', '星云支持语音转写吗？']:
            result = core.ask(question, product_id='nova_notes', version='2.0')
            self.assertNotEqual(result['evidence_match'], 'product_introduction')
        core.add_product('spec_only', '参数盒')
        core.add_document('spec_only', '1.0', '参数', '参数', 'spec.md', '参数盒附件上限为 50 MB。'.encode())
        unknown = core.ask('什么是参数盒', product_id='spec_only', version='1.0')
        self.assertEqual(unknown['status'], 'no_answer')

    def test_ambiguous_short_name_does_not_select_unrelated_product(self):
        core.add_product('nova_mail', '星云邮件')
        self.assertIsNone(core.detect_product('什么是星云', None, None))
        self.assertEqual(core.detect_product('什么是星云', 'nova_notes', None), 'nova_notes')

    def test_llm_mode_receives_scoped_overview_instead_of_rejecting_before_call(self):
        with patch.dict(os.environ, {'RAG_ANSWER_MODE': 'llm'}), \
                patch.object(core, 'llm_answer', return_value='星云支持创建文字笔记和标签。[1]') as generate:
            result = core.ask('什么是星云', product_id='nova_notes', version='2.0')
        self.assertEqual(result['generation_mode'], 'llm')
        self.assertEqual(result['status'], 'answered')
        self.assertIn('支持创建文字笔记和标签', generate.call_args.args[1][0]['text'])


if __name__ == '__main__':
    unittest.main()

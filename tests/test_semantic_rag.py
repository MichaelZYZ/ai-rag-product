import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from app import core, semantic, experiments
from review_results import aggregate
from fastapi.testclient import TestClient
from app.main import app


class SemanticRagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(core, 'DB_PATH', Path(self.temp.name) / 'test.sqlite3')
        self.db_patch.start()
        self.env = patch.dict(os.environ, {'EMBEDDING_PROVIDER': 'local', 'EMBEDDING_MODEL': 'test-fixture',
                                          'RAG_RETRIEVER': 'hash', 'RAG_ANSWER_MODE': 'auto'})
        self.env.start()
        core.init_db()
        for product in ('one', 'two'):
            core.add_product(product, product)
            for version in ('1', '2'):
                core.add_document(product, version, '说明', '资料', 'source.md',
                                  f'{product} {version} 的文件支持离线保存。'.encode())

    def tearDown(self):
        self.env.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    @unittest.skipUnless(importlib.util.find_spec('faiss'), 'optional FAISS dependency not installed')
    def test_real_faiss_scope_reuse_delete_and_identity(self):
        def vectors(texts):
            return semantic.normalize([[1, 0, len(text) / 100] for text in texts])
        with patch.object(semantic, 'embed', side_effect=vectors) as embed:
            first = semantic.index_chunks(core.connect)
            self.assertGreater(first['embedded'], 0)
            self.assertEqual(semantic.index_chunks(core.connect)['embedded'], 0)
            calls = embed.call_count
            hits = semantic.retrieve(core.connect, '离线保存', 'one', '2', 5)
            self.assertEqual(embed.call_count, calls + 1)  # query only; corpus vectors reused
            with core.connect() as db:
                ids = {r[0] for r in db.execute("SELECT id FROM chunks WHERE product_id='one' AND version='2'")}
                self.assertTrue(all(hit['chunk_id'] in ids for hit in hits))
                db.execute("DELETE FROM documents WHERE product_id='one' AND version='2'")
            self.assertEqual(semantic.retrieve(core.connect, '离线保存', 'one', '2', 5), [])
            with patch.dict(os.environ, {'EMBEDDING_MODEL': 'different-model'}):
                self.assertGreater(semantic.index_chunks(core.connect)['embedded'], 0)

    @unittest.skipUnless(importlib.util.find_spec('faiss'), 'optional FAISS dependency not installed')
    def test_semantic_chat_indexes_before_conversation_write_lock(self):
        with patch.dict(os.environ, {'RAG_RETRIEVER': 'semantic', 'RAG_ANSWER_MODE': 'extractive'}), \
                patch.object(semantic, 'embed', side_effect=lambda texts: semantic.normalize([[1, 1] for _ in texts])):
            result = core.ask('支持离线保存吗？', product_id='one', version='1')
        self.assertEqual(result['retriever'], 'semantic')
        self.assertEqual(result['status'], 'answered')

    def test_embedding_api_order_validation_and_normalization(self):
        payload = {'data': [{'index': 1, 'embedding': [0, 2]}, {'index': 0, 'embedding': [3, 0]}]}
        with patch.dict(os.environ, {'EMBEDDING_PROVIDER': 'api', 'EMBEDDING_BASE_URL': 'https://example.test/v1',
                                     'EMBEDDING_API_KEY': 'fixture'}):
            with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                np.testing.assert_allclose(semantic.embed(['a', 'b']), [[1, 0], [0, 1]])
            payload['data'][1]['index'] = 1
            with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaises(ValueError):
                    semantic.embed(['a', 'b'])
        for values in ([[0, 0]], [[float('nan'), 1]], [1, 2]):
            with self.assertRaises(ValueError):
                semantic.normalize(values)

    def test_strict_llm_never_counts_fallback_as_model_answer(self):
        sources = [{'chunk_id': 'fixture', 'text': '文件支持离线保存。', 'source': 'source.md',
                    'category': '说明', 'score': 0.9}]
        with patch.dict(os.environ, {'RAG_ANSWER_MODE': 'llm'}), patch.object(core, 'retrieve', return_value=sources), \
                patch.object(core, 'match_faq', return_value=None), patch.object(core, 'llm_answer', side_effect=TimeoutError):
            result = core.ask('能否离线保存？', product_id='one', version='1')
        self.assertEqual(result['generation_mode'], 'error')
        self.assertEqual(result['generation_error'], 'TimeoutError')
        self.assertEqual(result['status'], 'no_answer')
        self.assertNotIn('文件支持离线保存', result['answer'])
        with patch.dict(os.environ, {'RAG_ANSWER_MODE': 'llm'}), patch.object(core, 'retrieve', return_value=sources), \
                patch.object(core, 'match_faq', return_value=None), patch.object(core, 'llm_answer', return_value='文件支持离线保存。[1]'):
            result = core.ask('能否离线保存？', product_id='one', version='1')
        self.assertEqual(result['generation_mode'], 'llm')
        self.assertEqual(result['status'], 'answered')

    def test_human_review_empty_pending_tamper_and_partial_coverage(self):
        row = {'id': 'a', 'actual_status': 'answered', 'generation_mode': 'llm'}
        second = {**row, 'id': 'b'}
        report = {'runs': {'semantic_llm': {'comparisons': [row, second]}}}
        review = {'run': 'semantic_llm', 'case_id': 'a', 'record_digest': experiments.dataset_digest([row]),
                  'faithfulness': '', 'answer_relevance': '', 'reviewer': '', 'reason': ''}
        self.assertIsNone(aggregate(report, [review])['semantic_llm']['faithfulness'])
        review.update(faithfulness='1', answer_relevance='2', reviewer='测试评阅人', reason='有部分事实无证据')
        scores = aggregate(report, [review])['semantic_llm']
        self.assertEqual(scores['faithfulness'], 0.5)
        self.assertEqual(scores['coverage'], 0.5)
        with self.assertRaises(ValueError):
            aggregate(report, [review, review])
        review['record_digest'] = 'old snapshot'
        with self.assertRaises(ValueError):
            aggregate(report, [review])

    def test_invalid_threshold_rejected_before_writing_conversation(self):
        for value in ('nan', 'inf', '-0.1', '1.1'):
            with patch.dict(os.environ, {'RAG_MIN_SCORE': value}), self.assertRaises(ValueError):
                core.ask('问题', product_id='one', version='1')
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)

    def test_configuration_endpoints_report_state_and_redact_provider_errors(self):
        client = TestClient(app)
        with patch.dict(os.environ, {'LLM_API_KEY': 'never-include-this-secret'}):
            response = client.get('/api/rag/status')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('never-include-this-secret', response.text)
            self.assertGreater(response.json()['chunks'], 0)
            with patch.object(semantic, 'index_chunks', side_effect=RuntimeError('secret-service-detail')):
                failure = client.post('/api/rag/reindex')
            self.assertEqual(failure.status_code, 503)
            self.assertNotIn('secret-service-detail', failure.text)


if __name__ == '__main__':
    unittest.main()

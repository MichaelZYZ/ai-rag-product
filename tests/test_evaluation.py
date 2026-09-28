import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import core, main


class EvaluationTests(unittest.TestCase):
    def test_dashboard_metrics_use_snapshot_and_record_training_runs(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core, 'DB_PATH', Path(temp) / 'knowledge.sqlite3'):
            core.init_db()
            examples = json.loads((core.ROOT / 'data' / 'demo_knowledge.json').read_text(encoding='utf-8'))
            for item in examples:
                core.add_product(item['product_id'], item['product_name'], item['aliases'])
                core.add_document(item['product_id'], item['version'], item['category'],
                                  item['title'], item['source'], item['text'].encode())
            core.bootstrap_faqs('nova_notes', '2.0')
            with core.connect() as db:
                before = db.execute('SELECT count(*) FROM messages').fetchone()[0]
            result = main.evaluation()
            with core.connect() as db:
                after = db.execute('SELECT count(*) FROM messages').fetchone()[0]
            self.assertEqual(before, after)
            self.assertEqual(result['cases'], 8)
            self.assertEqual(result['retrieval_cases'], 4)
            self.assertEqual(sum(sum(row.values()) for row in result['confusion_matrix'].values()), 8)
            self.assertEqual(len(result['comparisons']), 8)
            self.assertEqual(len(result['training_history']), 1)
            self.assertEqual(result['training_history'][0]['product_id'], 'nova_notes')
            self.assertLessEqual(result['hit_at_k']['1'], result['hit_at_k']['3'])
            self.assertLessEqual(result['hit_at_k']['3'], result['hit_at_k']['5'])


if __name__ == '__main__':
    unittest.main()

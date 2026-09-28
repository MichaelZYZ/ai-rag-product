import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import core


class TrainingSummaryTests(unittest.TestCase):
    def test_repeat_training_reports_existing_questions(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core, 'DB_PATH', Path(temp) / 'knowledge.sqlite3'):
            core.init_db()
            core.add_product('cloud_box', '云盒')
            no_docs = core.bootstrap_faqs('cloud_box', '1.0')
            self.assertEqual(no_docs['documents_scanned'], 0)

            core.add_document('cloud_box', '1.0', '指南', '使用指南', 'guide.md',
                              '• 首次开机：长按电源键直到指示灯亮起，然后连接无线网络。'.encode())
            first = core.bootstrap_faqs('cloud_box', '1.0')
            repeated = core.bootstrap_faqs('cloud_box', '1.0')
            self.assertGreater(first['faqs_added'], 0)
            self.assertEqual(repeated['faqs_added'], 0)
            self.assertGreaterEqual(repeated['already_present'], first['faqs_added'])
            self.assertEqual(repeated['faqs_total'], first['faqs_total'])


if __name__ == '__main__':
    unittest.main()

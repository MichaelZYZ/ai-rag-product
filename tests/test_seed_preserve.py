import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SeedPreserveTests(unittest.TestCase):
    def test_launcher_seed_only_populates_empty_database(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / 'rag.sqlite3'
            env = {**os.environ, 'RAG_DB': str(db_path)}
            command = [sys.executable, 'seed.py', '--if-empty']
            first = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            with sqlite3.connect(db_path) as db:
                original = db.execute('SELECT id FROM documents ORDER BY id').fetchall()
            self.assertEqual(len(original), 3)

            second = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn('跳过演示数据导入', second.stdout)
            with sqlite3.connect(db_path) as db:
                after = db.execute('SELECT id FROM documents ORDER BY id').fetchall()
            self.assertEqual(after, original)


if __name__ == '__main__':
    unittest.main()

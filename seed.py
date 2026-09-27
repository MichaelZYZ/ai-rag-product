"""Import explicitly fictional sample knowledge; safe to run repeatedly."""
import json
import sys
from pathlib import Path
from app import core

core.init_db()
if '--if-empty' in sys.argv:
    with core.connect() as db:
        existing = db.execute('SELECT count(*) FROM documents').fetchone()[0]
    if existing:
        print(f'已发现 {existing} 份资料，跳过演示数据导入：{core.DB_PATH.resolve()}')
        sys.exit(0)
for item in json.loads((Path(__file__).parent / 'data' / 'demo_knowledge.json').read_text(encoding='utf-8')):
    core.add_product(item['product_id'], item['product_name'], item['aliases'])
    with core.connect() as db:
        db.execute('DELETE FROM documents WHERE product_id=? AND version=? AND source=?',
                   (item['product_id'], item['version'], item['source']))
    result = core.add_document(item['product_id'], item['version'], item['category'],
                               item['title'], item['source'], item['text'].encode())
    print(item['source'], result)

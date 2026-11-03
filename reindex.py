"""Build semantic vectors without changing the baseline vectors."""
import argparse
import json
from app import core, semantic

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product')
    parser.add_argument('--version')
    args = parser.parse_args()
    core.init_db()
    print(json.dumps(semantic.index_chunks(core.connect, args.product, args.version), ensure_ascii=False))

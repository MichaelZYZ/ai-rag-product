"""Validate human scores against an exact benchmark snapshot; aggregate coverage."""
import argparse
import csv
import json
from pathlib import Path
from app.experiments import dataset_digest


def aggregate(report, reviews):
    expected = {(run, row['id']): row for run, result in report['runs'].items() for row in result['comparisons']}
    seen, scores = set(), {}
    for row in reviews:
        key = (row['run'], row['case_id'])
        if key not in expected or key in seen:
            raise ValueError('评阅记录重复或不属于当前实验')
        seen.add(key)
        reference = expected[key]
        if row['record_digest'] != dataset_digest([reference]):
            raise ValueError('评阅记录与当前答案快照不一致')
        if ('actual_answer' in row and row['actual_answer'] != reference.get('actual_answer', '')):
            raise ValueError('评阅表中的答案已被修改，请使用原始答案评分')
        if 'evidence' in row and json.loads(row['evidence']) != reference.get('sources', []):
            raise ValueError('评阅表中的证据已被修改，请使用原始证据评分')
        if not row['faithfulness'] and not row['answer_relevance']:
            continue
        if reference['actual_status'] != 'answered' or reference['generation_mode'] == 'error':
            raise ValueError('只对成功回答评分；拒答质量由状态指标衡量')
        if not row['reviewer'].strip() or not row['reason'].strip():
            raise ValueError('评分必须包含评阅人和依据')
        if row['faithfulness'] not in ('0', '1', '2') or row['answer_relevance'] not in ('0', '1', '2'):
            raise ValueError('忠实度与相关性必须同时填写 0、1 或 2')
        scores.setdefault(key[0], []).append((int(row['faithfulness']) / 2, int(row['answer_relevance']) / 2))
    result = {}
    for run, data in report['runs'].items():
        values = scores.get(run, [])
        eligible = sum(r['actual_status'] == 'answered' and r['generation_mode'] != 'error' for r in data['comparisons'])
        result[run] = {'reviewed': len(values), 'eligible_answers': eligible,
                       'coverage': len(values) / eligible if eligible else None,
                       'faithfulness': sum(x[0] for x in values) / len(values) if values else None,
                       'answer_relevance': sum(x[1] for x in values) / len(values) if values else None}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = json.loads((args.directory / 'benchmark.json').read_text(encoding='utf-8'))
    with (args.directory / 'human_review.csv').open(encoding='utf-8-sig', newline='') as handle:
        result = aggregate(report, list(csv.DictReader(handle)))
    (args.directory / 'quality_scores.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

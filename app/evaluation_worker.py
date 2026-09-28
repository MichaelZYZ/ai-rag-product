"""Evaluate fixed examples against a database snapshot, without touching live data."""
import json

from . import core


def run():
    cases = json.loads((core.ROOT / 'data' / 'eval_cases.json').read_text(encoding='utf-8'))
    labels = ['answered', 'no_answer', 'handoff', 'other']
    matrix = {expected: {actual: 0 for actual in labels} for expected in labels}
    hit_counts = {1: 0, 3: 0, 5: 0}
    retrieval_cases = 0
    rows = []
    correct = 0
    for case in cases:
        expected_source = case.get('expected_source')
        if expected_source:
            retrieval_cases += 1
            sources = core.retrieve(case['question'], case['product_id'], case['version'], top_k=5)
            for k in hit_counts:
                hit_counts[k] += any(source['source'] == expected_source for source in sources[:k])
        result = core.ask(case['question'], product_id=case['product_id'], version=case['version'])
        expected_status = case['expected_status']
        actual_status = result['status'] if result['status'] in labels else 'other'
        matrix[expected_status if expected_status in labels else 'other'][actual_status] += 1
        status_ok = result['status'] == expected_status
        answer_ok = (case.get('expected_text', '') in result['answer']
                     if expected_status == 'answered' else status_ok)
        source_ok = (any(source['source'] == expected_source for source in result['sources'])
                     if expected_status == 'answered' else status_ok)
        passed = status_ok and answer_ok and source_ok
        correct += passed
        rows.append({
            'question': case['question'], 'product_id': case['product_id'],
            'version': case['version'], 'expected_status': expected_status,
            'actual_status': result['status'], 'expected_text': case.get('expected_text', ''),
            'actual_answer': result['answer'], 'expected_source': expected_source or '',
            'actual_sources': [source['source'] for source in result['sources']],
            'passed': passed,
        })
    return {'cases': len(cases), 'passed': correct, 'labels': labels,
            'confusion_matrix': matrix, 'retrieval_cases': retrieval_cases,
            'hit_at_k': {str(k): round(hit_counts[k] / retrieval_cases, 3)
                         if retrieval_cases else None for k in hit_counts},
            'comparisons': rows}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))

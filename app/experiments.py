"""Reproducible evaluation and explicit human quality assessment exports."""
import hashlib
import json
import statistics
import time
from . import core


def load_corpus():
    return json.loads((core.ROOT / 'data/demo_knowledge.json').read_text(encoding='utf-8')) + json.loads(
        (core.ROOT / 'data/course_knowledge.json').read_text(encoding='utf-8'))


def seed_experiment():
    core.init_db()
    for item in load_corpus():
        core.add_product(item['product_id'], item['product_name'], item['aliases'])
        core.add_document(item['product_id'], item['version'], item['category'], item['title'],
                          item['source'], item['text'].encode())


def run_cases(cases):
    rows = []
    for case in cases:
        session = None
        started = time.monotonic()
        try:
            for previous in case.get('history', []):
                session = core.ask(previous, session, case['product_id'], case['version'])['session_id']
            result = core.ask(case['question'], session, case['product_id'], case['version'])
            evidence = core.retrieve(result['rewritten_question'], case['product_id'], case['version'], top_k=5)
            status_ok = result['status'] == case['expected_status'] and not result['generation_error']
            answer_ok = (all(term in result['answer'] for term in case.get('expected_terms', []))
                         if case['expected_status'] == 'answered' else status_ok)
            expected = case.get('expected_evidence')
            hits = {str(k): any(case.get('expected_source') == s['source'] and expected in s['text']
                               for s in evidence[:k]) if expected else None for k in (1, 3, 5)}
            row = {**case, 'actual_status': result['status'], 'actual_answer': result['answer'],
                   'generation_mode': result['generation_mode'], 'generation_error': result['generation_error'],
                   'rewritten_question': result['rewritten_question'], 'sources': result['sources'],
                   'retrieved': evidence, 'status_ok': bool(status_ok), 'answer_keyword_ok': bool(answer_ok),
                   'hit_at_k': hits, 'passed': bool(status_ok and answer_ok),
                   'latency_ms': round((time.monotonic() - started) * 1000, 2)}
        except Exception as error:
            # Do not put provider error messages (which can contain credentials) into artifacts.
            row = {**case, 'actual_status': 'error', 'actual_answer': '', 'generation_mode': 'error',
                   'generation_error': type(error).__name__, 'sources': [], 'retrieved': [],
                   'status_ok': False, 'answer_keyword_ok': False, 'passed': False,
                   'hit_at_k': {str(k): False if case.get('expected_evidence') else None for k in (1, 3, 5)},
                   'latency_ms': round((time.monotonic() - started) * 1000, 2)}
        rows.append(row)
    count = len(rows)
    answerable = [r for r in rows if r['expected_status'] == 'answered']
    abstentions = [r for r in rows if r['expected_status'] == 'no_answer']
    retrieval = [r for r in rows if r.get('expected_evidence')]
    mean = lambda values: round(statistics.mean(values), 4) if values else None
    return {'cases': count, 'passed': sum(r['passed'] for r in rows),
            'status_accuracy': mean([r['status_ok'] for r in rows]),
            'answer_keyword_accuracy': mean([r['answer_keyword_ok'] and r['status_ok'] for r in answerable]),
            'abstention_accuracy': mean([r['status_ok'] for r in abstentions]),
            'hit_at_k': {str(k): mean([r['hit_at_k'][str(k)] for r in retrieval]) for k in (1, 3, 5)},
            'mean_latency_ms': mean([r['latency_ms'] for r in rows]),
            'generation_errors': sum(bool(r.get('generation_error')) for r in rows),
            'llm_answers': sum(r['generation_mode'] == 'llm' for r in rows),
            'faithfulness': None, 'answer_relevance': None,
            'quality_status': 'pending_human_review', 'comparisons': rows}


def dataset_digest(cases):
    return hashlib.sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

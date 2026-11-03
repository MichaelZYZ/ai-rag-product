"""Resolve product introduction questions to explicit, scoped source evidence."""
import json
import re


def subject(question):
    text = re.sub(r'[\s，。？！：；,.?!:;“”"()（）]+', '', question.lower())
    text = re.sub(r'^(?:请问|请|能否|能不能|可以)', '', text)
    if text in ('概念', '介绍', '产品介绍', '产品概述', '介绍一下', '简单介绍一下'):
        return ''
    for pattern in (r'^什么是(.+)$', r'^(.+?)(?:是什么|是干什么的|是做什么的)$',
                    r'^(?:介绍一下|介绍|简单介绍一下|简单介绍|请介绍一下)(.+)$'):
        match = re.fullmatch(pattern, text)
        if match:
            return match.group(1)
    return None


def matches(value, product):
    if value in ('', '它', '这个', '这个产品', '该产品'):
        return True
    names = [product['id'], product['name'], *json.loads(product['aliases'])]
    return any(value == name.lower() for name in names if name) or (
        len(value) >= 2 and product['name'].lower().startswith(value))


def resolve_product(question, products, explicit=None, prior=None):
    value = subject(question)
    if value is None or value in ('', '它', '这个', '这个产品', '该产品'):
        return None
    candidates = [p['id'] for p in products if matches(value, p)]
    if explicit in candidates:
        return explicit
    if prior in candidates:
        return prior
    return candidates[0] if len(candidates) == 1 else None


def retrieve(connect, question, product_id, version):
    """None means a normal question; an empty result means no overview evidence."""
    value = subject(question)
    if value is None:
        return None
    with connect() as db:
        product = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        if not product or not matches(value, product):
            return None
        faqs = db.execute('''SELECT * FROM faqs WHERE product_id=? AND version=?
            ORDER BY CASE kind WHEN 'manual' THEN 0 WHEN 'explicit' THEN 1
                     WHEN 'trained' THEN 2 ELSE 3 END,rowid''', (product_id, version)).fetchall()
        chunks = db.execute('SELECT * FROM chunks WHERE product_id=? AND version=? ORDER BY rowid',
                            (product_id, version)).fetchall()
    overview_faqs = [row for row in faqs if subject(row['question']) is not None
                     and matches(subject(row['question']), product)
                     and not re.fullmatch(r'https?://\S+', row['answer'].strip())]
    if overview_faqs:
        row = overview_faqs[0]
        conflict = len({r['answer'].strip() for r in overview_faqs if r['question'] == row['question']}) > 1
        source = {'chunk_id': row['id'], 'source': row['source'], 'category': row['category'],
                  'text': row['answer'], 'score': 1.0}
        return {'sources': [source], 'faq': {'answer': row['answer'], 'score': 1.0,
                                          'conflict': conflict, 'source': source}}
    name = re.escape(product['name'])
    definition = re.compile(name + r'\s*(?:\d+(?:\.\d+)*\s*)?(?:是(?:一款|一个|一种)|用于|主要用于|支持创建)')
    ranked = []
    for row in chunks:
        text = row['text']
        heading, separator, body = text.partition('\n')
        body = body if separator else text
        if re.fullmatch(r'https?://\S+', body.strip()):
            continue
        score = 2 if definition.search(body) else 0
        if separator and re.search(r'(产品介绍|产品概述|产品简介|基本介绍|产品概念)', heading) and len(body) >= 8:
            score += 1
        if score:
            ranked.append((score, {'chunk_id': row['id'], 'source': row['source'],
                                  'category': row['category'], 'text': text, 'score': 1.0}))
    ranked.sort(key=lambda pair: -pair[0])
    return {'sources': [r[1] for r in ranked[:3]], 'faq': None}

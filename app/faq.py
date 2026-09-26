"""Extract source-backed FAQ entries; generated questions never invent answers."""
from __future__ import annotations

import re

QUESTION = re.compile(r'^(?:Q(?:uestion)?|问(?:题)?)\s*[:：.、]\s*(.+)$', re.IGNORECASE)
ANSWER = re.compile(r'^(?:A(?:nswer)?|答(?:案)?)\s*[:：.、]\s*(.+)$', re.IGNORECASE)
INLINE = re.compile(r'^(?:Q(?:uestion)?|问(?:题)?)\s*[:：.、]\s*(.+?)\s*(?:A(?:nswer)?|答(?:案)?)\s*[:：.、]\s*(.+)$', re.IGNORECASE)
SECTION_QUESTIONS = {
    '产品介绍': ('什么是{product}？', '产品介绍'),
    '产品简介': ('什么是{product}？', '产品介绍'),
    '产品概述': ('什么是{product}？', '产品介绍'),
    '概述': ('什么是{product}？', '产品介绍'),
    '简介': ('什么是{product}？', '产品介绍'),
    '产品概览与硬件结构': ('{product}有哪些主要硬件结构？', '产品介绍'),
    '接口与包装': ('{product}的接口与包装有哪些说明？', '产品介绍'),
    '主要功能': ('{product}有哪些功能？', '功能介绍'),
    '核心功能': ('{product}有哪些功能？', '功能介绍'),
    '核心功能与内置软件': ('{product}有哪些主要功能？', '功能介绍'),
    '功能介绍': ('{product}有哪些功能？', '功能介绍'),
    '功能': ('{product}有哪些功能？', '功能介绍'),
    '首次开机': ('{product}如何首次开机？', '操作步骤'),
    '手势与按键': ('{product}有哪些常用手势和按键操作？', '操作步骤'),
    '系统设置与个性化': ('如何设置{product}？', '操作步骤'),
    '使用方法': ('如何使用{product}？', '操作步骤'),
    '操作步骤': ('如何使用{product}？', '操作步骤'),
    '快速入门': ('如何使用{product}？', '操作步骤'),
    '产品参数': ('{product}有哪些主要参数？', '参数限制'),
    '规格参数': ('{product}有哪些主要参数？', '参数限制'),
    '技术规格': ('{product}有哪些主要参数？', '参数限制'),
}


def _fact_body(line: str, product_name: str) -> str:
    body = line.strip()
    if product_name and body.startswith(product_name):
        body = body[len(product_name):].lstrip()
        body = re.sub(r'^\d+(?:\.\d+)*\s*', '', body)
        body = body.removeprefix('的').lstrip()
    return body.rstrip('。.')


def _rule_question(line: str, product_name: str):
    body = _fact_body(line, product_name)
    if not body or '?' in body or '？' in body:
        return None
    if product_name and line.startswith(product_name) and re.match(r'^(?:是一个|是一款|是一种|主要用于|用于)', body):
        return f'什么是{product_name}？', '产品介绍'
    limit = re.search(r'(.{0,25}?)最多支持\s*\d+(?:\.\d+)?\s*([^，。；]+)', body)
    if limit:
        return f'{limit.group(1)}最多支持多少{limit.group(2).strip()}？', '参数限制'
    size = re.search(r'(.{2,25}?(?:限制|上限))\s*(?:为|是|:|：)\s*.+?\d+\s*(?:MB|GB|KB|个|条|次)', body, re.IGNORECASE)
    if size:
        return f'{size.group(1)}是多少？', '参数限制'
    feature = re.match(r'^(?:不支持|支持)(.{2,70})$', body)
    if feature:
        return f'是否支持{feature.group(1).strip()}？', '功能支持'
    if '忘记密码' in body:
        return '忘记密码怎么办？', '故障处理'
    if re.search(r'(?:价格|售价)\s*(?:为|是|:|：)\s*\d+', body):
        return '价格是多少？', '价格'
    if re.search(r'(?:保修期|质保期)\s*(?:为|是|:|：)\s*.+', body):
        return '保修期是多久？', '售后保修'
    if body.startswith('适用于') and len(body) > 5:
        return '适用于哪些场景？', '适用场景'
    if body.startswith('兼容') and len(body) > 4:
        return '兼容哪些系统？', '兼容性'
    if '即可' in body and '导出' in body:
        format_name = re.search(r'\b(?:PDF|Word|Excel|CSV)\b', body, re.IGNORECASE)
        return f'如何导出{(" " + format_name.group(0)) if format_name else ""}？', '操作步骤'
    return None


def _section_faqs(lines, product_name):
    """Make broad common questions only from explicitly titled sections."""
    if not product_name:
        return []
    result, current, facts = [], None, []

    def flush():
        if current and facts:
            answer = '\n'.join(facts)
            if len(answer) >= 8:
                question, category = current
                result.append({'question': question.format(product=product_name),
                               'answer': answer, 'category': category, 'kind': 'auto'})

    for line in lines:
        if line.startswith('#'):
            flush()
            heading = re.sub(r'^[\d一二三四五六七八九十.、\s]+', '', line.lstrip('#').strip())
            current = SECTION_QUESTIONS.get(heading)
            facts = []
            continue
        if not current or QUESTION.match(line) or ANSWER.match(line) or line.endswith(('?', '？')):
            continue
        if len(facts) < 5 and sum(map(len, facts)) + len(line) <= 600:
            facts.append(line)
    flush()
    return result


def extract_faqs(text: str, product_name: str):
    """Return question/answer/category/kind rows from cleaned document text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    found, explicit_answer_lines, question, answer_lines = [], set(), None, []

    def flush():
        nonlocal question, answer_lines
        if question and answer_lines:
            found.append({'question': question.rstrip('？?') + '？',
                          'answer': '\n'.join(answer_lines), 'category': '文档 FAQ', 'kind': 'explicit'})
        question, answer_lines = None, []

    for index, line in enumerate(lines):
        if line.startswith('#'):
            flush()
            continue
        inline = INLINE.match(line)
        if inline:
            flush()
            found.append({'question': inline.group(1).strip().rstrip('？?') + '？',
                          'answer': inline.group(2).strip(), 'category': '文档 FAQ', 'kind': 'explicit'})
            explicit_answer_lines.add(index)
            continue
        q = QUESTION.match(line)
        a = ANSWER.match(line)
        if q or (line.endswith(('?', '？')) and len(line) <= 120):
            flush()
            question = (q.group(1) if q else line).strip()
            continue
        if a and question:
            answer_lines.append(a.group(1).strip())
            explicit_answer_lines.add(index)
            if answer_lines[-1].endswith(('。', '！', '!', '.')):
                flush()
        elif question:
            answer_lines.append(line)
            explicit_answer_lines.add(index)
            if answer_lines[-1].endswith(('。', '！', '!', '.')):
                flush()
    flush()

    for index, line in enumerate(lines):
        if line.startswith('#') or index in explicit_answer_lines or QUESTION.match(line) or ANSWER.match(line):
            continue
        result = _rule_question(line, product_name)
        if result:
            generated_question, category = result
            found.append({'question': generated_question, 'answer': line,
                          'category': category, 'kind': 'rule'})
            if category == '参数限制' and '上传限制' in generated_question and re.search(r'\d+\s*(?:MB|GB|KB)', line, re.IGNORECASE):
                found.append({'question': generated_question.replace('上传限制', '大小限制'),
                              'answer': line, 'category': category, 'kind': 'rule'})

    found.extend(_section_faqs(lines, product_name))

    # Keep the first source-backed answer for duplicate questions in one document.
    unique, seen = [], set()
    for item in found:
        key = re.sub(r'\s+', '', item['question']).lower()
        if key not in seen and item['answer'].strip():
            seen.add(key)
            unique.append(item)
    return unique


def extract_training_faqs(text: str, product_name: str):
    """Build focused customer questions from named facts and procedures.

    Answers are copied verbatim from one source line. This complements the broad
    section questions created at import time, so training has useful new work.
    """
    result, seen = [], set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or QUESTION.match(line) or ANSWER.match(line):
            continue
        body = re.sub(r'^[•●\-*]\s*', '', line).strip()
        if len(body) < 12 or len(body) > 800 or body.endswith(('?', '？')):
            continue
        match = re.match(r'^([^：:]{2,24})[：:]\s*(.{8,})$', body)
        if not match:
            continue
        topic, detail = match.group(1).strip(), match.group(2).strip()
        if not topic or re.search(r'[。；，?？]', topic) or not detail:
            continue
        if any(word in topic for word in ('资料核对', '阅读提示', '产品线提示', '来源', '参考资料')):
            continue
        if any(word in topic for word in ('无法', '故障', '黑屏', '死机', '发热', '忘记', '异常')):
            question, category = f'{product_name}{topic}怎么办？', '故障处理'
        elif any(word in topic for word in ('价格', '售价', '费用')):
            question, category = f'{product_name}{topic}是多少？', '价格'
        elif any(word in topic for word in ('保修', '质保')):
            question, category = f'{product_name}{topic}是多久？', '售后保修'
        elif any(word in topic for word in ('参数', '容量', '限制', '上限', '尺寸', '规格')):
            question, category = f'{product_name}{topic}是多少？', '参数限制'
        elif '版本' in topic:
            question, category = f'{product_name}的{topic}是什么？', '参数限制'
        elif 'SIM' in topic.upper():
            question, category = f'{product_name}如何安装或设置{topic}？', '操作步骤'
        elif 'Face ID' in topic:
            question, category = f'{product_name}如何设置{topic}？', '操作步骤'
        elif any(word in topic for word in ('顶部', '底部', '左侧', '右侧', '背面', '屏幕')):
            question, category = f'{product_name}的{topic}有什么？', '产品介绍'
        elif any(word in topic for word in ('设置', '开机', '关机', '重启', '截图', '连接', '配对', '导出', '清洁', '充电', '操作', '使用')) or '→' in detail:
            question, category = f'{product_name}如何{topic}？', '操作步骤'
        elif any(word in topic for word in ('功能', '支持', '兼容', '接口')):
            question, category = f'{product_name}的{topic}有哪些？', '功能介绍'
        else:
            question, category = f'{product_name}的{topic}有什么说明？', '功能介绍'
        key = re.sub(r'\s+', '', question).lower()
        if key not in seen:
            seen.add(key)
            result.append({'question': question, 'answer': detail,
                           'category': category, 'kind': 'trained'})
    return result

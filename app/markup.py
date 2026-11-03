"""Remove presentation markup while retaining factual text and table relationships."""
import re


def inline(text):
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: m[1] + ' (' + m[2] + ')', text)
    text = re.sub(r'(`+)(.*?)\1', r'\2', text)
    for delimiter in ('**', '__'):
        text = re.sub(re.escape(delimiter) + r'(\S(?:.*?\S)?)' + re.escape(delimiter), r'\1', text)
    text = re.sub(r'(?<![\w*])\*(\S(?:.*?\S)?)\*(?![\w*])', r'\1', text)
    text = re.sub(r'(?<!\w)_(\S(?:.*?\S)?)_(?!\w)', r'\1', text)
    # Strikethrough conveys obsolete text, so retain its meaning explicitly.
    text = re.sub(r'~~(.+?)~~', r'(已删除: \1)', text)
    text = re.sub(r'</?(?:strong|b|em|i|u|span|code)(?:\s[^>]*)?>', '', text, flags=re.I)
    return text


def table_cells(line):
    return [cell.strip().replace('\\|', '|') for cell in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def clean_markup(text, markdown=False):
    stats = {'markup_lines_cleaned': 0, 'markup_lines_removed': 0, 'table_rows_converted': 0}
    if markdown:
        text = re.sub(r'\A\s*---\s*\n(.*?)\n---\s*(?:\n|\Z)', lambda m: m[1] + '\n', text, count=1, flags=re.S)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    lines, result, fence, index = text.splitlines(), [], None, 0
    while index < len(lines):
        original = lines[index]
        line = original.strip()
        index += 1
        if markdown and re.match(r'^(`{3,}|~{3,})', line):
            marker = line[0]
            fence = None if fence == marker else marker
            stats['markup_lines_removed'] += 1
            continue
        if fence:
            result.append(original)
            continue
        if (markdown and index < len(lines) and re.fullmatch(r'\s*(?:={3,}|-{3,})\s*', lines[index])
                and line and len(line) <= 80 and not re.search(r'[。:：;；!?！？]', line)
                and not re.match(r'^[#>*+\-]', line)):
            result.append('# ' + inline(line))
            index += 1
            stats['markup_lines_cleaned'] += 1
            stats['markup_lines_removed'] += 1
            continue
        if markdown and '|' in line and index < len(lines):
            headers = table_cells(line)
            separators = table_cells(lines[index])
            if len(headers) > 1 and len(headers) == len(separators) and all(re.fullmatch(r':?-{3,}:?', c) for c in separators):
                index += 1
                stats['markup_lines_removed'] += 2
                while index < len(lines) and '|' in lines[index]:
                    cells = table_cells(lines[index])
                    if len(cells) != len(headers):
                        break
                    if len(headers) == 2 and headers[0] in ('项目', '参数', '功能', '名称', '问题', '字段', '指标'):
                        rendered = inline(cells[0]) + ': ' + inline(cells[1])
                    else:
                        rendered = '; '.join(inline(h) + ': ' + inline(v) for h, v in zip(headers, cells))
                    result.append(rendered)
                    stats['table_rows_converted'] += 1
                    index += 1
                continue
        if markdown and re.fullmatch(r'(?:[-*_]\s*){3,}', line):
            stats['markup_lines_removed'] += 1
            continue
        if markdown:
            line = re.sub(r'^>\s+', '', line)
            task = re.match(r'^[-+*]\s+\[([ xX])\]\s*(.*)', line)
            if task:
                line = ('已勾选: ' if task[1].lower() == 'x' else '未勾选: ') + task[2]
            else:
                line = re.sub(r'^[-+*]\s+', '', line)
            line = re.sub(r'^(#{1,6})\s+(.+?)\s+#+$', r'\1 \2', line)
            line = inline(line)
        # DOCX/PDF/plain text can also contain decorative bullet glyphs.
        line = re.sub(r'^[•●◦▪]\s*', '', line)
        if line != original:
            stats['markup_lines_cleaned'] += 1
        result.append(line)
    return '\n'.join(result), stats

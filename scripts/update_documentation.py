"""Validate documentation sources and local links before generating Word/PPT."""
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    'README.md', 'docs/README.md', 'docs/guides/PROJECT_OVERVIEW.md',
    'docs/guides/BUSINESS_OPERATIONS.md', 'docs/guides/PROJECT_QA_GUIDE.md',
    'docs/guides/FREE_API_SETUP.md', 'docs/guides/EVALUATION_GUIDE.md',
    'docs/design/ARCHITECTURE.md', 'docs/design/SYSTEM_DESIGN.md',
    'docs/design/RAG_IMPLEMENTATION.md', 'docs/analysis/FAILURE_ANALYSIS.md',
    'docs/course/SUBMISSION_CHECKLIST.md', 'docs/exports/README.md'
]


def validate():
    failures = []
    for name in SOURCES:
        if not (ROOT / name).is_file():
            failures.append('缺少文档：' + name)
    for path in [ROOT / 'README.md', *(ROOT / 'docs').rglob('*.md')]:
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = unquote(target.split('#', 1)[0])
            if not target or '://' in target or target.startswith('mailto:'):
                continue
            if not (path.parent / target).exists():
                failures.append(str(path.relative_to(ROOT)) + ' → ' + target)
    if failures:
        raise SystemExit('\n'.join(failures))
    print('文档来源与本地链接检查通过。更新 Word/PPT：python -m scripts.build_deliverables')


if __name__ == '__main__':
    validate()

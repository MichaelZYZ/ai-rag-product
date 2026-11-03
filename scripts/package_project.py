"""Package reproducible course sources, without secrets or live user databases."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    archive = output / 'rag_course_project.zip'
    roots = ['app', 'tests', 'prompts', 'docs', 'scripts', 'reports/latest', 'data', '.github']
    allowed = {'.py', '.json', '.csv', '.md', '.html', '.txt', '.png', '.pdf', '.docx', '.pptx', '.ps1', '.yml', '.yaml'}
    candidates = [p for name in roots for p in (ROOT / name).rglob('*') if p.is_file()]
    candidates += [p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py', '.md', '.txt', '.ps1', '.bat', '.command', '.docx'}]
    candidates.append(ROOT / '.env.example')
    selected = sorted({p for p in candidates if (p.suffix in allowed or p.parent == ROOT)
                       and '__pycache__' not in p.parts and not p.name.startswith('~$')
                       and p.suffix not in {'.sqlite3', '.db', '.pyc'} and not p.name.startswith('.env')
                       and not p.name.endswith('.llm.json') and not p.name.startswith('.llm-')})
    selected.append(ROOT / '.env.example')
    selected.append(ROOT / '.gitignore')
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in selected}
    with ZipFile(archive, 'w', ZIP_DEFLATED) as handle:
        for path in selected:
            handle.write(path, str(path.relative_to(ROOT)))
        handle.writestr('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    print(archive, len(manifest), 'files; SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()

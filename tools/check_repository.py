#!/usr/bin/env python3
"""Check public-tree shape, documentation links, and common accidental leaks.

A useful publishing guard, not a complete secret scanner or privacy proof.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def public_files():
    # Check staged/tracked contents when Git exists, otherwise the prepared tree.
    if (ROOT / '.git').exists():
        names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        if any(names):
            return [ROOT / name for name in names if name]
    return [p for p in ROOT.rglob('*') if p.is_file()
            and not any(part in ('.git', '.local', '__pycache__', '.venv') for part in p.relative_to(ROOT).parts)]


def main():
    errors = []
    required = ['README.md', 'README.en.md', 'LICENSE', 'AGENTS.md', 'CLAUDE.md',
                'workflow.json', 'skills/firetv-burton/SKILL.md']
    for name in required:
        if not (ROOT / name).is_file(): errors.append('Missing: ' + name)
    workflow = json.loads((ROOT / 'workflow.json').read_text())
    if workflow['executes_automatically'] is not False:
        errors.append('Operator workflow must not execute automatically')
    for path in public_files():
        relative = path.relative_to(ROOT)
        if any(part in ('.local', 'private', 'backups') for part in relative.parts):
            errors.append('Private directory tracked: ' + str(relative))
        if path.suffix.lower() in ('.apk', '.apks', '.arm', '.db', '.tar', '.tgz', '.log', '.pem', '.key'):
            errors.append('Private/third-party artifact: ' + str(relative))
        try: text = path.read_text()
        except (UnicodeError, OSError):
            errors.append('Unexpected binary/unreadable file: ' + str(relative)); continue
        checks = [r'/' + r'Users/[^/\s]+/', r'\b(?:192\.168|10)\.[0-9]{1,3}\.[0-9]{1,3}\b',
                  r'\bG[0-9A-Z]{15}\b', r'gh[pousr]_[A-Za-z0-9]{20,}', r'github_pat_[A-Za-z0-9_]{20,}']
        if any(re.search(pattern, text) for pattern in checks):
            errors.append('Possible identifier/credential: ' + str(relative))
        if path.suffix == '.md':
            for link in re.findall(r'(?<!!)\[[^\]]+\]\(([^\s)]+)\)', text):
                target = link.split('#', 1)[0]
                if target and not re.match(r'^[a-zA-Z]+:', target) and not target.startswith('$'):
                    if not (path.parent / target).exists():
                        errors.append('Broken local link in ' + str(relative) + ': ' + target)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Public-tree checks passed: no known private artifacts, identifiers or broken local links.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

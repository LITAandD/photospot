"""Reject drift between the full runtime's pins and the smaller Vercel runtime."""
from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    pins = {}
    for line in (root / 'constraints.txt').read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            dep = Requirement(line)
            pins[canonicalize_name(dep.name)] = str(dep.specifier)
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    for text in project['dependencies']:
        dep = Requirement(text)
        if pins.get(canonicalize_name(dep.name)) != str(dep.specifier):
            raise ValueError(f'Preview dependency differs from constraints.txt: {dep.name}')
    for line in (root / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or line.startswith('-'):
            continue
        dep = Requirement(line)
        pin = pins.get(canonicalize_name(dep.name), '')
        if not pin.startswith('==') or pin[2:] not in dep.specifier:
            raise ValueError(f'Missing or incompatible runtime pin: {dep.name}')


if __name__ == '__main__':
    check()
    print('Runtime and preview dependency pins agree.')

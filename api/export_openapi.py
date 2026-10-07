"""코드에서 OpenAPI 명세 생성: python -m api.export_openapi > openapi.yaml"""
import sys
import argparse
from pathlib import Path

import yaml

from .main import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = yaml.safe_dump(create_app().openapi(), allow_unicode=True, sort_keys=False)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(rendered)

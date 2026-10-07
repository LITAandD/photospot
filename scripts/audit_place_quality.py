"""Audit stored place/object classification; --apply backs up before correction."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from pipeline import place_catalog as catalog, place_quality as quality


def audit(*, apply=False, path=None, report=None):
    now = datetime.now(timezone.utc)
    report = Path(report or catalog.ROOT / "artifacts" / "place-quality-audit.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    with catalog.connect(path) as conn:
        before = conn.execute("SELECT count(*) FROM places WHERE active=1").fetchone()[0]
        if apply:
            backup = report.parent / ("places-before-quality-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite3")
            with sqlite3.connect(backup) as target: conn.backup(target)
        changes = quality.reconcile(conn, apply=apply)
        excluded = sum(c["action"] == "exclude" for c in changes)
    result = {"rule_version": quality.RULE_VERSION, "checked_at": now.isoformat(), "applied": apply,
              "backup": str(backup) if backup else None, "checked_active": before,
              "remaining_active": before - excluded, "excluded": excluded,
              "reclassified": len(changes) - excluded,
              "reasons": dict(Counter(c["reason"] for c in changes)), "changes": changes}
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(apply=args.apply, report=args.report)
    print(json.dumps({k: v for k, v in result.items() if k != "changes"}, ensure_ascii=True))


if __name__ == "__main__": main()

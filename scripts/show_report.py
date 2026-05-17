"""
Execution Report Viewer — aggregate metrics from past runs.

Usage:
  python scripts/show_report.py                         # all runs in logs/quizzes
  python scripts/show_report.py --dir logs/quizzes      # explicit dir
  python scripts/show_report.py --last 10               # most recent N runs
  python scripts/show_report.py --save logs/reports/latest.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.metrics.reports import ExecutionReporter


def main() -> None:
    p = argparse.ArgumentParser(description="Show execution report")
    p.add_argument("--dir",  default="logs/quizzes", help="Artifacts directory")
    p.add_argument("--last", type=int, default=0,    help="Show only last N runs")
    p.add_argument("--save", default="",             help="Save report JSON to this path")
    args = p.parse_args()

    reporter   = ExecutionReporter()
    quizzes_dir = Path(args.dir)

    if not quizzes_dir.exists():
        print(f"Directory not found: {quizzes_dir}")
        sys.exit(1)

    manifests = sorted(
        quizzes_dir.glob("*/manifest.json"),
        key=lambda p: p.stat().st_mtime,
    )

    if args.last:
        manifests = manifests[-args.last:]

    batch = reporter.from_manifests(manifests)
    reporter.print_summary(batch)

    if args.save:
        reporter.save_report(batch, Path(args.save))
        print(f"Saved → {args.save}")


if __name__ == "__main__":
    main()

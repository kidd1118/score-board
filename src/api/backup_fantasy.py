"""Back up the fantasy database, or export it as JSON.

    python backup_fantasy.py                 # copy to data/backups/fantasy-<time>.db
    python backup_fantasy.py --json out.json # readable export (same shape as the old fantasy.json)

Safe to run while the servers are up.
"""
import argparse
import json
from pathlib import Path

import store


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", metavar="FILE", help="export everything as JSON instead of copying the database")
    args = parser.parse_args()
    if args.json:
        Path(args.json).write_text(json.dumps(store.load(), ensure_ascii=False, indent=2))
        print(f"exported to {args.json}")
    else:
        print(f"backed up to {store.backup()}")


if __name__ == "__main__":
    main()

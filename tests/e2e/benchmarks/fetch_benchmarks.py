from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "sources.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch third-party benchmark collections for e2e experiments.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--source", action="append", help="Fetch only the named source. Repeatable.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    selected = set(args.source or [])
    for source in manifest.get("sources", []):
        name = str(source["name"])
        if selected and name not in selected:
            continue
        fetch_source(source, dry_run=args.dry_run)
    return 0


def fetch_source(source: dict, *, dry_run: bool = False) -> None:
    name = str(source["name"])
    git_url = str(source["git"])
    ref = str(source.get("ref", "main"))
    target = ROOT / str(source["path"])
    command: list[str]
    if target.exists():
        command = ["git", "-C", str(target), "fetch", "--depth", "1", "origin", ref]
        checkout = ["git", "-C", str(target), "checkout", "FETCH_HEAD"]
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", "--depth", "1", "--branch", ref, git_url, str(target)]
        checkout = []
    print(f"{name}: {' '.join(command)}")
    if dry_run:
        return
    subprocess.run(command, check=True)
    if checkout:
        print(f"{name}: {' '.join(checkout)}")
        subprocess.run(checkout, check=True)


if __name__ == "__main__":
    raise SystemExit(main())

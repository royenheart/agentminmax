# E2E Benchmarks

This directory stores benchmark management metadata, not full third-party benchmark datasets.

- `sources.json` lists upstream benchmark repositories.
- `fetch_benchmarks.py` fetches those repositories into `third_party/`.
- `third_party/` is intentionally ignored by git.
- Root-level `experiments.py` runs the AgentMinMax live tasks and writes outputs to `runs/`.

Fetch benchmark sources:

```bash
python tests/e2e/benchmarks/fetch_benchmarks.py
```

Prepare the built-in live tasks without invoking Codex:

```bash
python experiments.py --dry-run
```

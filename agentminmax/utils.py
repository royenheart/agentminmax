from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=None)
def load_data_json(filename: str) -> dict[str, Any]:
    return json.loads(resources.files("agentminmax").joinpath(f"data/{filename}").read_text(encoding="utf-8"))

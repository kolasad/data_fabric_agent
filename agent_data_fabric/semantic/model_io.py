"""Serialize and load the semantic model (YAML or JSON)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from agent_data_fabric.core.models import SemanticModel


def _is_json(path: Path) -> bool:
    return path.suffix.lower() == ".json"


def save_model(model: SemanticModel, path: str | Path) -> Path:
    """Write ``model`` to ``path``. Format is chosen by file extension."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = model.model_dump(mode="json")

    if _is_json(path):
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    path.write_text(text, encoding="utf-8")
    return path


def load_model(path: str | Path) -> SemanticModel:
    """Load a semantic model previously written by :func:`save_model`."""

    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if _is_json(path) else yaml.safe_load(text)
    return SemanticModel.model_validate(data)

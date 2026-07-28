import json
from pathlib import Path
from typing import Any


def save_json(data: dict[str, Any], path: Path) -> None:
    """Guarda JSON legible y crea carpetas intermedias."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    """Carga un JSON desde disco."""
    return json.loads(path.read_text(encoding="utf-8"))

from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from config import OUTPUTS_DIR
from config import PROJECTS_DIR
from core.json_store import save_json
from core.time_utils import now_iso
from workflows.resource_filter_rules import DEFAULT_RESOURCE_FILTER_RULES


def create_project(
    project_id: str,
    name: str,
    start_url: str,
    actor: str,
    description: str = "",
) -> dict[str, str]:
    """Crea los archivos iniciales de un proyecto editable."""
    project_id = project_id.strip()
    name = name.strip()
    start_url = start_url.strip()
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", project_id):
        raise ValueError(
            "El identificador solo puede contener letras minusculas, numeros y guiones bajos."
        )
    if not name:
        raise ValueError("El nombre del proyecto es obligatorio.")
    parsed_url = urlparse(start_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("La URL inicial debe ser una direccion HTTP o HTTPS valida.")
    project_dir = PROJECTS_DIR / project_id
    output_dir = OUTPUTS_DIR / project_id
    snapshots_dir = project_dir / "snapshots"

    if project_dir.exists():
        raise ValueError(f"Ya existe un proyecto con el identificador {project_id}.")
    project_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    _touch_gitkeep(snapshots_dir)

    timestamp = now_iso()
    save_json(
        _project_payload(project_id, name, start_url, description, timestamp),
        project_dir / "project.json",
    )
    save_json(
        _candidate_links_payload(project_id, start_url, timestamp),
        project_dir / "candidate_links.json",
    )
    save_json(
        _human_review_payload(project_id, timestamp),
        project_dir / "human_review.json",
    )
    save_json(
        _change_log_payload(project_id, actor, timestamp),
        project_dir / "change_log.json",
    )
    save_json(
        _resource_filter_rules_payload(project_id, timestamp),
        project_dir / "resource_filter_rules.json",
    )
    save_json(
        _resource_review_payload(project_id, timestamp),
        project_dir / "resource_review.json",
    )

    return {
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
    }


def _project_payload(
    project_id: str,
    name: str,
    start_url: str,
    description: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "name": name,
        "start_url": start_url,
        "status": "draft",
        "created_at": timestamp,
        "updated_at": timestamp,
        "current_snapshot": None,
        "description": description,
    }


def _candidate_links_payload(
    project_id: str,
    source_url: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "source_url": source_url,
        "generated_at": timestamp,
        "links": [],
    }


def _human_review_payload(project_id: str, timestamp: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "review_status": "not_started",
        "updated_at": timestamp,
        "decisions": [],
    }


def _change_log_payload(project_id: str, actor: str, timestamp: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "events": [
            {
                "event_id": "event_001",
                "timestamp": timestamp,
                "actor": actor,
                "action": "create_project",
                "target_type": "project",
                "target_id": project_id,
                "summary": "Se creo el proyecto editable.",
                "before": None,
                "after": {
                    "status": "draft",
                },
            }
        ],
    }


def _resource_filter_rules_payload(project_id: str, timestamp: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "updated_at": timestamp,
        "rules": DEFAULT_RESOURCE_FILTER_RULES,
    }


def _resource_review_payload(project_id: str, timestamp: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "review_status": "not_started",
        "updated_at": timestamp,
        "decisions": [],
    }


def _touch_gitkeep(path: Path) -> None:
    gitkeep = path / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")

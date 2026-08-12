from pathlib import Path
from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso
from workflows.effective_project_state import resolve_effective_project_state


LIFECYCLE_STATUSES = {"active", "inactive"}


def save_node_lifecycle_status(
    project_id: str,
    link_id: str,
    status: str,
    notes: str,
    actor: str,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Activa o desactiva un nodo sin borrar evidencia ni decisiones previas."""
    if status not in LIFECYCLE_STATUSES:
        raise ValueError(f"Estado de ciclo de vida inválido: {status}")

    root = projects_dir or PROJECTS_DIR
    project_dir = root / project_id
    state = resolve_effective_project_state(project_id, root)
    node = next(
        (item for item in state["nodes"] if item.get("link_id") == link_id),
        None,
    )
    if not node:
        raise ValueError(f"No existe el nodo {link_id}")
    if not node.get("participates_in_model"):
        raise ValueError("Solo se puede cambiar el ciclo de vida de un nodo incluido")

    lifecycle_path = project_dir / "lifecycle_review.json"
    change_log_path = project_dir / "change_log.json"
    payload = _load_or_create(project_id, lifecycle_path)
    previous = _find_state(payload.get("node_states", []), link_id)
    timestamp = now_iso()
    decision = {
        "link_id": link_id,
        "status": status,
        "notes": notes.strip(),
        "reviewed_by": actor,
        "reviewed_at": timestamp,
    }
    _upsert_state(payload, decision)
    payload["updated_at"] = timestamp
    save_json(payload, lifecycle_path)

    if change_log_path.exists():
        change_log = load_json(change_log_path)
        change_log.setdefault("events", []).append(
            {
                "event_id": f"event_{len(change_log.get('events', [])) + 1:03d}",
                "timestamp": timestamp,
                "actor": actor,
                "action": "deactivate_node" if status == "inactive" else "reactivate_node",
                "target_type": "candidate_link",
                "target_id": link_id,
                "summary": f"Se cambió {link_id} a estado {status} sin borrar trabajo previo.",
                "before": previous,
                "after": decision,
            }
        )
        save_json(change_log, change_log_path)
    return decision


def node_lifecycle_impact(
    state: dict[str, Any],
    link_id: str,
) -> dict[str, Any]:
    """Calcula el impacto de desactivar un nodo usando el estado vigente."""
    relations = [
        item
        for item in state.get("relations", [])
        if item.get("source_link_id") == link_id and item.get("status") == "active"
    ]
    resources = {
        item.get("canonical_resource_key"): item
        for item in state.get("canonical_resources", [])
    }
    orphaned = 0
    still_used = 0
    become_node_only = 0
    for relation in relations:
        resource = resources.get(relation.get("canonical_resource_key"), {})
        active_sources = resource.get("active_source_link_ids", [])
        if len(active_sources) <= 1:
            orphaned += 1
        else:
            still_used += 1
            if len(active_sources) == 2:
                become_node_only += 1
    return {
        "relation_count": len(relations),
        "orphaned_resource_count": orphaned,
        "still_used_resource_count": still_used,
        "become_node_only_count": become_node_only,
    }


def _load_or_create(project_id: str, path: Path) -> dict[str, Any]:
    if path.exists():
        return load_json(path)
    return {
        "schema_version": "0.1",
        "project_id": project_id,
        "updated_at": None,
        "node_states": [],
    }


def _find_state(states: list[dict[str, Any]], link_id: str) -> dict[str, Any] | None:
    for item in states:
        if item.get("link_id") == link_id:
            return dict(item)
    return None


def _upsert_state(payload: dict[str, Any], decision: dict[str, Any]) -> None:
    states = payload.setdefault("node_states", [])
    for index, item in enumerate(states):
        if item.get("link_id") == decision["link_id"]:
            states[index] = decision
            return
    states.append(decision)

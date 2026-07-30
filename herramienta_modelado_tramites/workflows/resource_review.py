from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso


RESOURCE_USE_VALUES = {
    "process_as_context",
    "show_as_link",
    "discard",
    "review_later",
}

RESOURCE_SCOPE_VALUES = {
    "node_only",
    "shared",
}


def save_resource_decision(
    project_id: str,
    source_link_id: str,
    resource_id: str,
    use: str,
    scope: str,
    notes: str,
    actor: str,
) -> dict[str, Any]:
    """Guarda que debe hacer la herramienta con un recurso interno."""
    if use not in RESOURCE_USE_VALUES:
        raise ValueError(f"Uso invalido: {use}. Valores: {sorted(RESOURCE_USE_VALUES)}")
    if scope not in RESOURCE_SCOPE_VALUES:
        raise ValueError(
            f"Alcance invalido: {scope}. Valores: {sorted(RESOURCE_SCOPE_VALUES)}"
        )

    project_dir = PROJECTS_DIR / project_id
    resource_review_path = project_dir / "resource_review.json"
    node_resources_path = project_dir / "node_resources.json"
    change_log_path = project_dir / "change_log.json"

    node_resources = load_json(node_resources_path)
    resource = _find_resource(node_resources, source_link_id, resource_id)
    resource_review = _load_or_create_resource_review(project_id, resource_review_path)
    change_log = load_json(change_log_path)
    previous_decision = _find_decision(
        resource_review.get("decisions", []),
        source_link_id,
        resource_id,
    )
    timestamp = now_iso()

    decision = {
        "decision_id": f"{source_link_id}::{resource_id}",
        "source_link_id": source_link_id,
        "resource_id": resource_id,
        "url": resource.get("url"),
        "title": resource.get("title"),
        "resource_type": resource.get("resource_type"),
        "use": use,
        "scope": scope,
        "notes": notes,
        "reviewed_by": actor,
        "reviewed_at": timestamp,
        "decision_source": "individual",
        "overrides_group": bool(
            previous_decision
            and previous_decision.get("decision_source")
            == "auxiliary_group"
        ),
        "overridden_group_id": (
            previous_decision.get("source_group_id")
            if previous_decision
            and previous_decision.get("decision_source")
            == "auxiliary_group"
            else None
        ),
    }

    _upsert_decision(resource_review, decision)
    resource_review["review_status"] = _review_status(
        _reviewable_resources(node_resources),
        resource_review.get("decisions", []),
    )
    resource_review["updated_at"] = timestamp
    save_json(resource_review, resource_review_path)

    action = (
        "classify_resource"
        if previous_decision is None
        else "update_resource_decision"
    )
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "target_type": "internal_resource",
            "target_id": decision["decision_id"],
            "summary": (
                f"Se guardo decision de recurso {decision['decision_id']}: "
                f"{use} / {scope}."
            ),
            "before": previous_decision,
            "after": decision,
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "source_link_id": source_link_id,
        "resource_id": resource_id,
        "use": use,
        "scope": scope,
        "resource_review_path": str(resource_review_path),
    }


def _load_or_create_resource_review(
    project_id: str,
    resource_review_path,
) -> dict[str, Any]:
    if resource_review_path.exists():
        return load_json(resource_review_path)
    return {
        "project_id": project_id,
        "review_status": "not_started",
        "updated_at": now_iso(),
        "decisions": [],
    }


def _find_resource(
    node_resources: dict[str, Any],
    source_link_id: str,
    resource_id: str,
) -> dict[str, Any]:
    for page in node_resources.get("pages", []):
        if page.get("link_id") != source_link_id:
            continue
        for resource in page.get("resources", []):
            if resource.get("resource_id") == resource_id:
                return resource
        for resource in page.get("discarded_resources", []):
            if resource.get("resource_id") == resource_id:
                return resource
    raise ValueError(
        f"No existe recurso {source_link_id}::{resource_id} en node_resources.json"
    )


def _find_decision(
    decisions: list[dict[str, Any]],
    source_link_id: str,
    resource_id: str,
) -> dict[str, Any] | None:
    for decision in decisions:
        if (
            decision.get("source_link_id") == source_link_id
            and decision.get("resource_id") == resource_id
        ):
            return dict(decision)
    return None


def _upsert_decision(
    resource_review: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    decisions = resource_review.setdefault("decisions", [])
    for index, current in enumerate(decisions):
        if current.get("decision_id") == decision["decision_id"]:
            decisions[index] = decision
            return
    decisions.append(decision)


def _reviewable_resources(node_resources: dict[str, Any]) -> list[tuple[str, str]]:
    resources = []
    for page in node_resources.get("pages", []):
        source_link_id = page.get("link_id")
        for resource in page.get("resources", []):
            resources.append((source_link_id, resource.get("resource_id")))
    return resources


def _review_status(
    resources: list[tuple[str, str]],
    decisions: list[dict[str, Any]],
) -> str:
    reviewed = {
        (decision.get("source_link_id"), decision.get("resource_id"))
        for decision in decisions
        if decision.get("use")
    }
    if resources and all(resource in reviewed for resource in resources):
        return "complete"
    if reviewed:
        return "in_progress"
    return "not_started"

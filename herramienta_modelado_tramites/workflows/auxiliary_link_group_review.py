from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso
from workflows.resource_review import RESOURCE_SCOPE_VALUES
from workflows.resource_review import RESOURCE_USE_VALUES


IDENTITY_DECISIONS = {
    "confirmed_same",
    "keep_separate",
    "review_later",
}


def save_auxiliary_group_decision(
    project_id: str,
    group_id: str,
    identity_decision: str,
    default_use: str,
    scope: str,
    selected_canonical_url: str,
    display_name: str,
    notes: str,
    actor: str,
) -> dict[str, Any]:
    """Guarda una decisión grupal y la materializa por aparición."""
    if identity_decision not in IDENTITY_DECISIONS:
        raise ValueError(f"Decisión de identidad inválida: {identity_decision}")
    if default_use not in RESOURCE_USE_VALUES:
        raise ValueError(f"Uso inválido: {default_use}")
    if scope not in RESOURCE_SCOPE_VALUES:
        raise ValueError(f"Alcance inválido: {scope}")

    project_dir = PROJECTS_DIR / project_id
    analysis_path = project_dir / "auxiliary_link_analysis.json"
    group_review_path = project_dir / "auxiliary_link_group_review.json"
    resource_review_path = project_dir / "resource_review.json"
    change_log_path = project_dir / "change_log.json"

    analysis = load_json(analysis_path)
    group, group_kind = _find_group(analysis, group_id)
    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    group_items = [
        appearances[appearance_id]
        for appearance_id in group.get("appearance_ids", [])
        if appearance_id in appearances
    ]
    allowed_urls = {
        url
        for item in group_items
        for url in {
            item.get("detected_url"),
            item.get("candidate_canonical_url"),
        }
        if url
    }
    if selected_canonical_url and selected_canonical_url not in allowed_urls:
        raise ValueError("La URL canónica debe pertenecer al grupo")
    if identity_decision == "confirmed_same" and not selected_canonical_url:
        raise ValueError("Selecciona una URL canónica para confirmar el grupo")

    timestamp = now_iso()
    group_review = _load_or_create_group_review(
        project_id,
        group_review_path,
    )
    previous_group_decision = _find_group_decision(
        group_review.get("decisions", []),
        group_id,
    )
    decision = {
        "group_id": group_id,
        "group_kind": group_kind,
        "identity_decision": identity_decision,
        "default_use": default_use,
        "scope": scope,
        "selected_canonical_url": selected_canonical_url or None,
        "display_name": display_name.strip(),
        "notes": notes.strip(),
        "appearance_ids": [
            item.get("appearance_id") for item in group_items
        ],
        "reviewed_by": actor,
        "reviewed_at": timestamp,
        "analysis_generated_at": analysis.get("generated_at"),
    }

    resource_review = _load_or_create_resource_review(
        project_id,
        resource_review_path,
    )
    applied_ids, exception_ids = _materialize_group_decision(
        resource_review,
        decision,
        group_items,
    )
    decision["materialization"] = {
        "applied_appearance_ids": applied_ids,
        "preserved_individual_exception_ids": exception_ids,
    }
    _upsert_group_decision(group_review, decision)
    group_review["review_status"] = "in_progress"
    group_review["updated_at"] = timestamp
    save_json(group_review, group_review_path)

    resource_review["review_status"] = _resource_review_status(
        analysis,
        resource_review.get("decisions", []),
    )
    resource_review["updated_at"] = timestamp
    save_json(resource_review, resource_review_path)

    change_log = load_json(change_log_path)
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": (
                "review_auxiliary_link_group"
                if previous_group_decision is None
                else "update_auxiliary_link_group_review"
            ),
            "target_type": "auxiliary_link_group",
            "target_id": group_id,
            "summary": (
                f"Se revisó {group_id}: {identity_decision} / "
                f"{default_use}. Se aplicó a {len(applied_ids)} apariciones "
                f"y se conservaron {len(exception_ids)} excepciones."
            ),
            "before": previous_group_decision,
            "after": decision,
        }
    )
    save_json(change_log, change_log_path)
    return decision


def _materialize_group_decision(
    resource_review: dict[str, Any],
    group_decision: dict[str, Any],
    appearances: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    decisions = resource_review.setdefault("decisions", [])
    by_id = {
        item.get("decision_id"): (index, item)
        for index, item in enumerate(decisions)
    }
    applied_ids = []
    exception_ids = []

    for appearance in appearances:
        appearance_id = appearance.get("appearance_id")
        previous_entry = by_id.get(appearance_id)
        previous = previous_entry[1] if previous_entry else None
        if previous and previous.get("overrides_group") is True:
            exception_ids.append(appearance_id)
            continue

        inherited = {
            "decision_id": appearance_id,
            "source_link_id": appearance.get("source_node_id"),
            "resource_id": appearance.get("resource_id"),
            "url": appearance.get("detected_url"),
            "canonical_url": group_decision.get("selected_canonical_url"),
            "title": appearance.get("label"),
            "resource_type": appearance.get("detected_resource_type"),
            "use": group_decision.get("default_use"),
            "scope": group_decision.get("scope"),
            "notes": group_decision.get("notes"),
            "reviewed_by": group_decision.get("reviewed_by"),
            "reviewed_at": group_decision.get("reviewed_at"),
            "decision_source": "auxiliary_group",
            "source_group_id": group_decision.get("group_id"),
            "inherited": True,
        }
        if previous_entry:
            decisions[previous_entry[0]] = inherited
        else:
            decisions.append(inherited)
        applied_ids.append(appearance_id)

    return applied_ids, exception_ids


def reapply_saved_auxiliary_group_decisions(
    project_id: str,
    actor: str,
) -> dict[str, Any]:
    """Recalcula la materialización sin pedir nuevas decisiones humanas."""
    project_dir = PROJECTS_DIR / project_id
    analysis = load_json(project_dir / "auxiliary_link_analysis.json")
    group_review_path = project_dir / "auxiliary_link_group_review.json"
    resource_review_path = project_dir / "resource_review.json"
    change_log_path = project_dir / "change_log.json"
    group_review = load_json(group_review_path)
    resource_review = _load_or_create_resource_review(
        project_id,
        resource_review_path,
    )
    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    timestamp = now_iso()
    all_applied = []
    all_exceptions = []

    for decision in group_review.get("decisions", []):
        items = [
            appearances[appearance_id]
            for appearance_id in decision.get("appearance_ids", [])
            if appearance_id in appearances
        ]
        applied_ids, exception_ids = _materialize_group_decision(
            resource_review,
            decision,
            items,
        )
        decision["materialization"] = {
            "applied_appearance_ids": applied_ids,
            "preserved_individual_exception_ids": exception_ids,
            "reconciled_at": timestamp,
        }
        all_applied.extend(applied_ids)
        all_exceptions.extend(exception_ids)

    group_review["updated_at"] = timestamp
    save_json(group_review, group_review_path)
    resource_review["review_status"] = _resource_review_status(
        analysis,
        resource_review.get("decisions", []),
    )
    resource_review["updated_at"] = timestamp
    save_json(resource_review, resource_review_path)

    change_log = load_json(change_log_path)
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "reapply_auxiliary_link_group_decisions",
            "target_type": "project",
            "target_id": project_id,
            "summary": (
                f"Se reaplicaron decisiones de "
                f"{len(group_review.get('decisions', []))} grupos a "
                f"{len(all_applied)} apariciones; se conservaron "
                f"{len(all_exceptions)} excepciones explícitas."
            ),
            "before": None,
            "after": {
                "applied_appearance_ids": all_applied,
                "preserved_individual_exception_ids": all_exceptions,
            },
        }
    )
    save_json(change_log, change_log_path)
    return {
        "group_count": len(group_review.get("decisions", [])),
        "applied_appearance_ids": all_applied,
        "preserved_individual_exception_ids": all_exceptions,
    }


def _find_group(
    analysis: dict[str, Any],
    group_id: str,
) -> tuple[dict[str, Any], str]:
    collections = {
        "agenda": "agenda_candidates",
        "normalized": "normalized_equivalence_candidates",
        "exact": "exact_url_groups",
    }
    for group_kind, collection in collections.items():
        for group in analysis.get(collection, []):
            if group.get("group_id") == group_id:
                return group, group_kind
    raise ValueError(f"No existe el grupo {group_id}")


def _load_or_create_group_review(project_id: str, path) -> dict[str, Any]:
    if path.exists():
        return load_json(path)
    return {
        "schema_version": "0.1",
        "project_id": project_id,
        "review_status": "not_started",
        "updated_at": now_iso(),
        "decisions": [],
    }


def _load_or_create_resource_review(project_id: str, path) -> dict[str, Any]:
    if path.exists():
        return load_json(path)
    return {
        "project_id": project_id,
        "review_status": "not_started",
        "updated_at": now_iso(),
        "decisions": [],
    }


def _find_group_decision(
    decisions: list[dict[str, Any]],
    group_id: str,
) -> dict[str, Any] | None:
    for decision in decisions:
        if decision.get("group_id") == group_id:
            return dict(decision)
    return None


def _upsert_group_decision(
    review: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    decisions = review.setdefault("decisions", [])
    for index, current in enumerate(decisions):
        if current.get("group_id") == decision["group_id"]:
            decisions[index] = decision
            return
    decisions.append(decision)


def _resource_review_status(
    analysis: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> str:
    reviewable_ids = {
        item.get("appearance_id")
        for item in analysis.get("appearances", [])
        if item.get("filter_status") == "reviewable"
    }
    decided_ids = {
        item.get("decision_id")
        for item in decisions
        if item.get("use")
    }
    if reviewable_ids and reviewable_ids <= decided_ids:
        return "complete"
    if decided_ids:
        return "in_progress"
    return "not_started"

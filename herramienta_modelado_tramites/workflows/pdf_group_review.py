from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso
from workflows.resource_review import RESOURCE_USE_VALUES


IDENTITY_DECISIONS = {
    "confirmed_same",
    "keep_separate",
    "review_later",
}


def save_pdf_family_decision(
    project_id: str,
    family_id: str,
    default_use: str,
    selected_canonical_url: str,
    display_name: str,
    notes: str,
    actor: str,
) -> dict[str, Any]:
    """Confirma manualmente una familia completa antes de la verificación."""
    if default_use not in RESOURCE_USE_VALUES:
        raise ValueError(f"Uso inválido: {default_use}")
    project_dir = PROJECTS_DIR / project_id
    analysis = load_json(project_dir / "pdf_analysis.json")
    family = _find_group(analysis, family_id)
    allowed_ids = set(family.get("appearance_ids", []))
    allowed_urls = _appearance_urls(analysis, allowed_ids)
    if selected_canonical_url not in allowed_urls:
        raise ValueError("Selecciona una URL canónica de la familia")

    review_path = project_dir / "pdf_group_review.json"
    change_log_path = project_dir / "change_log.json"
    review = _load_or_create_review(project_id, review_path)
    previous = _find_family_decision(
        review.get("family_decisions", []),
        family_id,
    )
    timestamp = now_iso()
    decision = {
        "family_id": family_id,
        "appearance_ids": sorted(allowed_ids),
        "identity_decision": "confirmed_same_manually",
        "default_use": default_use,
        "selected_canonical_url": selected_canonical_url,
        "display_name": display_name.strip(),
        "notes": notes.strip(),
        "reviewed_by": actor,
        "reviewed_at": timestamp,
        "analysis_generated_at": analysis.get("generated_at"),
        "verification_reconciliation": "pending",
    }
    _upsert_family_decision(review, decision)
    applied_ids, exception_ids = _materialize_pdf_decision(
        project_dir,
        analysis,
        family.get("appearance_ids", []),
        decision,
        family_id,
    )
    decision["materialization"] = {
        "applied_appearance_ids": applied_ids,
        "preserved_individual_exception_ids": exception_ids,
        "reconciled_at": timestamp,
    }
    review["updated_at"] = timestamp
    save_json(review, review_path)

    change_log = load_json(change_log_path)
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "confirm_pdf_family_manually",
            "target_type": "pdf_family",
            "target_id": family_id,
            "summary": f"Se confirmó manualmente la familia PDF {family_id}.",
            "before": previous,
            "after": decision,
        }
    )
    save_json(change_log, change_log_path)
    return decision


def save_pdf_partition_decision(
    project_id: str,
    family_id: str,
    partition_id: str,
    identity_decision: str,
    default_use: str,
    selected_canonical_url: str,
    display_name: str,
    notes: str,
    actor: str,
) -> dict[str, Any]:
    """Guarda la revisión humana sin modificar el análisis regenerable."""
    if identity_decision not in IDENTITY_DECISIONS:
        raise ValueError(f"Decisión de identidad inválida: {identity_decision}")
    if default_use not in RESOURCE_USE_VALUES:
        raise ValueError(f"Uso inválido: {default_use}")

    project_dir = PROJECTS_DIR / project_id
    analysis_path = project_dir / "pdf_analysis.json"
    review_path = project_dir / "pdf_group_review.json"
    change_log_path = project_dir / "change_log.json"

    analysis = load_json(analysis_path)
    family = _find_group(analysis, family_id)
    partition = _find_partition(family, partition_id)
    allowed_appearances = set(partition.get("appearance_ids", []))

    allowed_urls = _appearance_urls(analysis, allowed_appearances)
    if selected_canonical_url and selected_canonical_url not in allowed_urls:
        raise ValueError("La URL canónica debe pertenecer al grupo")
    if identity_decision == "confirmed_same" and not selected_canonical_url:
        raise ValueError("Selecciona una URL canónica para confirmar el grupo")

    review = _load_or_create_review(project_id, review_path)
    previous = _find_decision(review.get("decisions", []), partition_id)
    timestamp = now_iso()
    decision = {
        "family_id": family_id,
        "partition_id": partition_id,
        "identity_decision": identity_decision,
        "default_use": default_use,
        "selected_canonical_url": selected_canonical_url or None,
        "display_name": display_name.strip(),
        "notes": notes.strip(),
        "reviewed_by": actor,
        "reviewed_at": timestamp,
        "analysis_generated_at": analysis.get("generated_at"),
    }
    _upsert_decision(review, decision)
    applied_ids = []
    exception_ids = []
    if identity_decision == "confirmed_same":
        applied_ids, exception_ids = _materialize_pdf_decision(
            project_dir,
            analysis,
            partition.get("appearance_ids", []),
            decision,
            partition_id,
        )
    decision["materialization"] = {
        "applied_appearance_ids": applied_ids,
        "preserved_individual_exception_ids": exception_ids,
        "reconciled_at": timestamp,
    }
    review["review_status"] = _review_status(
        _all_partition_ids(analysis),
        review.get("decisions", []),
    )
    review["updated_at"] = timestamp
    save_json(review, review_path)

    change_log = load_json(change_log_path)
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": (
                "review_pdf_group" if previous is None
                else "update_pdf_group_review"
            ),
            "target_type": "pdf_group",
            "target_id": partition_id,
            "summary": (
                f"Se guardó la revisión de la partición PDF {partition_id}: "
                f"{identity_decision} / {default_use}."
            ),
            "before": previous,
            "after": decision,
        }
    )
    save_json(change_log, change_log_path)
    return decision


def _find_group(
    analysis: dict[str, Any],
    group_id: str,
) -> dict[str, Any]:
    for group in analysis.get("proposed_groups", []):
        if group.get("group_id") == group_id:
            return group
    raise ValueError(f"No existe el grupo {group_id} en pdf_analysis.json")


def _find_partition(
    family: dict[str, Any],
    partition_id: str,
) -> dict[str, Any]:
    for partition in family.get("verification", {}).get("partitions", []):
        if partition.get("partition_id") == partition_id:
            return partition
    raise ValueError(f"No existe la partición {partition_id}")


def _appearance_urls(
    analysis: dict[str, Any],
    appearance_ids: set[str],
) -> set[str]:
    return {
        item.get("detected_url")
        for item in analysis.get("appearances", [])
        if item.get("appearance_id") in appearance_ids
        and item.get("detected_url")
    }


def _materialize_pdf_decision(
    project_dir,
    analysis: dict[str, Any],
    appearance_ids: list[str],
    group_decision: dict[str, Any],
    source_group_id: str,
) -> tuple[list[str], list[str]]:
    """Proyecta una decisión PDF grupal sobre sus apariciones individuales."""
    resource_review_path = project_dir / "resource_review.json"
    if resource_review_path.exists():
        resource_review = load_json(resource_review_path)
    else:
        resource_review = {
            "project_id": analysis.get("project_id"),
            "review_status": "not_started",
            "updated_at": now_iso(),
            "decisions": [],
        }
    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    selected = [
        appearances[item_id]
        for item_id in appearance_ids
        if item_id in appearances
    ]
    scope = (
        "shared"
        if len({item.get("source_node_id") for item in selected}) > 1
        else "node_only"
    )
    decisions = resource_review.setdefault("decisions", [])
    by_id = {
        item.get("decision_id"): (index, item)
        for index, item in enumerate(decisions)
    }
    applied_ids = []
    exception_ids = []
    for appearance in selected:
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
            "canonical_resource_id": source_group_id,
            "title": appearance.get("label"),
            "resource_type": "pdf",
            "use": group_decision.get("default_use"),
            "scope": scope,
            "notes": group_decision.get("notes"),
            "reviewed_by": group_decision.get("reviewed_by"),
            "reviewed_at": group_decision.get("reviewed_at"),
            "decision_source": "pdf_group",
            "source_group_id": source_group_id,
            "inherited": True,
        }
        if previous_entry:
            decisions[previous_entry[0]] = inherited
        else:
            decisions.append(inherited)
        applied_ids.append(appearance_id)
    resource_review["updated_at"] = now_iso()
    save_json(resource_review, resource_review_path)
    return applied_ids, exception_ids


def _load_or_create_review(project_id: str, path) -> dict[str, Any]:
    if path.exists():
        return load_json(path)
    return {
        "schema_version": "0.1",
        "project_id": project_id,
        "review_status": "not_started",
        "updated_at": now_iso(),
        "decisions": [],
    }


def _find_decision(
    decisions: list[dict[str, Any]],
    partition_id: str,
) -> dict[str, Any] | None:
    for decision in decisions:
        if decision.get("partition_id") == partition_id:
            return dict(decision)
    return None


def _find_family_decision(
    decisions: list[dict[str, Any]],
    family_id: str,
) -> dict[str, Any] | None:
    for decision in decisions:
        if decision.get("family_id") == family_id:
            return dict(decision)
    return None


def _upsert_family_decision(
    review: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    decisions = review.setdefault("family_decisions", [])
    for index, current in enumerate(decisions):
        if current.get("family_id") == decision["family_id"]:
            decisions[index] = decision
            return
    decisions.append(decision)


def _upsert_decision(
    review: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    decisions = review.setdefault("decisions", [])
    for index, current in enumerate(decisions):
        if current.get("partition_id") == decision["partition_id"]:
            decisions[index] = decision
            return
    decisions.append(decision)


def _review_status(
    partition_ids: set[str],
    decisions: list[dict[str, Any]],
) -> str:
    decided = {
        item.get("partition_id")
        for item in decisions
        if item.get("identity_decision") in IDENTITY_DECISIONS
    }
    if partition_ids and partition_ids <= decided:
        return "complete"
    if decided:
        return "in_progress"
    return "not_started"


def _all_partition_ids(analysis: dict[str, Any]) -> set[str]:
    return {
        partition.get("partition_id")
        for family in analysis.get("proposed_groups", [])
        for partition in family.get("verification", {}).get("partitions", [])
    }

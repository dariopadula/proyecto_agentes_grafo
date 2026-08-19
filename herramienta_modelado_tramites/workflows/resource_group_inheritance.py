from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso


def restore_resource_group_inheritance(
    project_id: str,
    source_link_id: str,
    resource_id: str,
    actor: str,
) -> dict[str, Any]:
    """Reemplaza una excepción individual por la decisión grupal vigente."""
    project_dir = PROJECTS_DIR / project_id
    review_path = project_dir / "resource_review.json"
    change_log_path = project_dir / "change_log.json"
    review = load_json(review_path)
    decision_id = f"{source_link_id}::{resource_id}"
    previous = _find_decision(review, decision_id)
    if previous.get("decision_source") != "individual" or not previous.get(
        "overrides_group"
    ):
        raise ValueError("El recurso no es una excepción individual a un grupo")

    group_id = previous.get("overridden_group_id") or previous.get(
        "source_group_id"
    )
    if not group_id:
        raise ValueError("La excepción no conserva el identificador del grupo")

    inherited = _restore_from_auxiliary_group(
        project_dir,
        decision_id,
        group_id,
        actor,
    ) or _restore_from_pdf_group(
        project_dir,
        decision_id,
        group_id,
        actor,
    )
    if inherited is None:
        raise ValueError(
            "La aparición ya no pertenece a un grupo con una decisión vigente"
        )

    decisions = review.setdefault("decisions", [])
    index = next(
        index
        for index, item in enumerate(decisions)
        if item.get("decision_id") == decision_id
    )
    decisions[index] = inherited
    review["updated_at"] = inherited["reviewed_at"]
    save_json(review, review_path)

    change_log = load_json(change_log_path)
    change_log.setdefault("events", []).append(
        {
            "event_id": f"event_{len(change_log.get('events', [])) + 1:03d}",
            "timestamp": inherited["reviewed_at"],
            "actor": actor,
            "action": "restore_resource_group_inheritance",
            "target_type": "internal_resource",
            "target_id": decision_id,
            "summary": (
                f"Se eliminó la excepción individual de {decision_id} y "
                f"se restauró la decisión vigente de {group_id}."
            ),
            "before": previous,
            "after": inherited,
        }
    )
    save_json(change_log, change_log_path)
    return inherited


def _restore_from_auxiliary_group(
    project_dir,
    appearance_id: str,
    group_id: str,
    actor: str,
) -> dict[str, Any] | None:
    analysis_path = project_dir / "auxiliary_link_analysis.json"
    review_path = project_dir / "auxiliary_link_group_review.json"
    if not analysis_path.exists() or not review_path.exists():
        return None
    analysis = load_json(analysis_path)
    group = next(
        (
            item
            for collection in (
                "agenda_candidates",
                "normalized_equivalence_candidates",
                "exact_url_groups",
            )
            for item in analysis.get(collection, [])
            if item.get("group_id") == group_id
        ),
        None,
    )
    if not group or appearance_id not in group.get("appearance_ids", []):
        return None
    group_review = load_json(review_path)
    group_decision = next(
        (
            item
            for item in group_review.get("decisions", [])
            if item.get("group_id") == group_id
        ),
        None,
    )
    if not group_decision or set(group_decision.get("appearance_ids", [])) != set(
        group.get("appearance_ids", [])
    ):
        return None
    appearance = next(
        item
        for item in analysis.get("appearances", [])
        if item.get("appearance_id") == appearance_id
    )
    source_link_id, resource_id = appearance_id.split("::", 1)
    return {
        "decision_id": appearance_id,
        "source_link_id": source_link_id,
        "resource_id": resource_id,
        "url": appearance.get("detected_url"),
        "canonical_url": group_decision.get("selected_canonical_url"),
        "title": appearance.get("label"),
        "resource_type": appearance.get("detected_resource_type"),
        "use": group_decision.get("default_use"),
        "scope": group_decision.get("scope"),
        "notes": group_decision.get("notes"),
        "reviewed_by": actor,
        "reviewed_at": now_iso(),
        "decision_source": "auxiliary_group",
        "source_group_id": group_id,
        "inherited": True,
    }


def _restore_from_pdf_group(
    project_dir,
    appearance_id: str,
    group_id: str,
    actor: str,
) -> dict[str, Any] | None:
    analysis_path = project_dir / "pdf_analysis.json"
    review_path = project_dir / "pdf_group_review.json"
    if not analysis_path.exists() or not review_path.exists():
        return None
    analysis = load_json(analysis_path)
    review = load_json(review_path)
    family = next(
        (
            item
            for item in analysis.get("proposed_groups", [])
            if item.get("group_id") == group_id
        ),
        None,
    )
    group_decision = None
    member_ids: list[str] = []
    if family and appearance_id in family.get("appearance_ids", []):
        candidate = next(
            (
                item
                for item in review.get("family_decisions", [])
                if item.get("family_id") == group_id
            ),
            None,
        )
        if candidate and set(candidate.get("appearance_ids", [])) == set(
            family.get("appearance_ids", [])
        ):
            group_decision = candidate
            member_ids = family.get("appearance_ids", [])
    if group_decision is None:
        for candidate_family in analysis.get("proposed_groups", []):
            partition = next(
                (
                    item
                    for item in candidate_family.get("verification", {}).get(
                        "partitions", []
                    )
                    if item.get("partition_id") == group_id
                    and appearance_id in item.get("appearance_ids", [])
                ),
                None,
            )
            if not partition:
                continue
            group_decision = next(
                (
                    item
                    for item in review.get("decisions", [])
                    if item.get("partition_id") == group_id
                    and item.get("identity_decision") == "confirmed_same"
                ),
                None,
            )
            if group_decision:
                member_ids = partition.get("appearance_ids", [])
            break
    if group_decision is None:
        return None

    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    appearance = appearances.get(appearance_id)
    if not appearance:
        return None
    scope = (
        "shared"
        if len(
            {
                appearances[item_id].get("source_node_id")
                for item_id in member_ids
                if item_id in appearances
            }
        )
        > 1
        else "node_only"
    )
    source_link_id, resource_id = appearance_id.split("::", 1)
    return {
        "decision_id": appearance_id,
        "source_link_id": source_link_id,
        "resource_id": resource_id,
        "url": appearance.get("detected_url"),
        "canonical_url": group_decision.get("selected_canonical_url"),
        "canonical_resource_id": group_id,
        "title": appearance.get("label"),
        "resource_type": "pdf",
        "use": group_decision.get("default_use"),
        "scope": scope,
        "notes": group_decision.get("notes"),
        "reviewed_by": actor,
        "reviewed_at": now_iso(),
        "decision_source": "pdf_group",
        "source_group_id": group_id,
        "inherited": True,
    }


def _find_decision(review: dict[str, Any], decision_id: str) -> dict[str, Any]:
    decision = next(
        (
            dict(item)
            for item in review.get("decisions", [])
            if item.get("decision_id") == decision_id
        ),
        None,
    )
    if decision is None:
        raise ValueError(f"No existe una decisión para {decision_id}")
    return decision

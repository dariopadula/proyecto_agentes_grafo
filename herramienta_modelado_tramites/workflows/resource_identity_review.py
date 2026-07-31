from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso
from workflows.resource_review import save_resource_decision


IDENTITY_ACTIONS = {
    "assign_existing",
    "create_family",
    "keep_individual",
    "exclude",
}
ASSIGNMENT_MODES = {"candidate_verify", "direct_confirm"}


def save_resource_identity_decision(
    project_id: str,
    appearance_id: str,
    action: str,
    target_family_id: str,
    assignment_mode: str,
    new_family_name: str,
    notes: str,
    actor: str,
) -> dict[str, Any]:
    """Resuelve una aparición PDF sin confundir identidad con uso."""
    if action not in IDENTITY_ACTIONS:
        raise ValueError("Acción de identidad inválida")
    if action in {"assign_existing", "create_family"} and assignment_mode not in ASSIGNMENT_MODES:
        raise ValueError("Selecciona cómo incorporar el recurso")

    project_dir = PROJECTS_DIR / project_id
    analysis_path = project_dir / "pdf_analysis.json"
    analysis = load_json(analysis_path)
    appearance = _find_appearance(analysis, appearance_id)
    if action == "assign_existing":
        _find_family(analysis, target_family_id)
    if action == "create_family" and not new_family_name.strip():
        raise ValueError("Escribe un nombre para la familia nueva")

    review_path = project_dir / "resource_identity_review.json"
    review = (
        load_json(review_path)
        if review_path.exists()
        else {
            "schema_version": "0.1",
            "project_id": project_id,
            "updated_at": now_iso(),
            "decisions": [],
        }
    )
    previous = next(
        (
            dict(item)
            for item in review.get("decisions", [])
            if item.get("appearance_id") == appearance_id
        ),
        None,
    )
    timestamp = now_iso()
    decision = {
        "appearance_id": appearance_id,
        "resource_type": "pdf",
        "action": action,
        "target_family_id": target_family_id or None,
        "assignment_mode": assignment_mode or None,
        "new_family_name": new_family_name.strip() or None,
        "notes": notes.strip(),
        "reviewed_by": actor,
        "reviewed_at": timestamp,
    }
    _upsert(review.setdefault("decisions", []), decision)
    review["updated_at"] = timestamp
    save_json(review, review_path)

    updated_analysis = apply_pdf_membership_decisions(analysis, review)
    save_json(review, review_path)
    save_json(updated_analysis, analysis_path)

    if action == "exclude":
        save_resource_decision(
            project_id=project_id,
            source_link_id=appearance.get("source_node_id"),
            resource_id=appearance.get("resource_id"),
            use="discard",
            scope="node_only",
            notes=notes,
            actor=actor,
        )
    elif action == "assign_existing" and assignment_mode == "direct_confirm":
        _inherit_existing_family_decision(
            project_dir,
            updated_analysis,
            target_family_id,
            appearance_id,
        )

    _log_change(project_dir, project_id, decision, previous)
    return decision


def apply_pdf_membership_decisions(
    analysis: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    """Aplica el overlay humano a familias regenerables."""
    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    groups = analysis.setdefault("proposed_groups", [])
    for decision in review.get("decisions", []):
        appearance_id = decision.get("appearance_id")
        if appearance_id not in appearances:
            continue
        for group in groups:
            if appearance_id in group.get("appearance_ids", []):
                group["appearance_ids"].remove(appearance_id)
                _reset_family(group)
        if decision.get("action") == "assign_existing":
            group = _find_family(analysis, decision.get("target_family_id"))
            group.setdefault("appearance_ids", []).append(appearance_id)
            group["appearance_ids"] = sorted(set(group["appearance_ids"]))
            group["membership_source"] = "human_overlay"
            _reset_family(group)
        elif decision.get("action") == "create_family":
            group_id = decision.get("target_family_id") or _manual_family_id(
                groups,
                appearance_id,
            )
            decision["target_family_id"] = group_id
            group = next(
                (item for item in groups if item.get("group_id") == group_id),
                None,
            )
            if group is None:
                appearance = appearances[appearance_id]
                group = {
                    "group_id": group_id,
                    "group_kind": "human_created_family",
                    "certainty": "human_proposed",
                    "evidence": {
                        "field": "human_decision",
                        "value": decision.get("new_family_name"),
                        "appearance_count": 1,
                        "analysis_statuses": ["not_verified"],
                    },
                    "appearance_ids": [appearance_id],
                    "proposed_canonical_resource": {
                        "resource_id": group_id,
                        "display_name": decision.get("new_family_name"),
                        "resource_type": "pdf",
                        "proposed_canonical_url": appearance.get("detected_url"),
                        "selected_canonical_url": None,
                        "alternative_urls": [],
                        "suggested_default_use": "review_later",
                        "review_status": "pending_human_confirmation",
                    },
                    "membership_source": "human_overlay",
                }
                groups.append(group)
            _reset_family(group)
    groups[:] = [group for group in groups if group.get("appearance_ids")]
    for group in groups:
        group.setdefault("evidence", {})["appearance_count"] = len(
            group.get("appearance_ids", [])
        )
    return analysis


def _inherit_existing_family_decision(
    project_dir,
    analysis: dict[str, Any],
    family_id: str,
    appearance_id: str,
) -> None:
    review_path = project_dir / "pdf_group_review.json"
    if not review_path.exists():
        return
    review = load_json(review_path)
    family_decision = next(
        (
            item
            for item in review.get("family_decisions", [])
            if item.get("family_id") == family_id
        ),
        None,
    )
    if family_decision is None:
        return
    from workflows.pdf_group_review import _materialize_pdf_decision

    _materialize_pdf_decision(
        project_dir,
        analysis,
        [appearance_id],
        family_decision,
        family_id,
    )


def _reset_family(group: dict[str, Any]) -> None:
    appearance_ids = group.get("appearance_ids", [])
    group["verification"] = {
        "status": "not_started",
        "verified_at": None,
        "all_appearances_same": None,
        "partitions": [],
        "unverified_appearance_ids": list(appearance_ids),
    }


def _manual_family_id(groups: list[dict[str, Any]], appearance_id: str) -> str:
    used = {group.get("group_id") for group in groups}
    base = "pdf_manual_" + appearance_id.replace("::", "_")
    candidate = base
    number = 2
    while candidate in used:
        candidate = f"{base}_{number}"
        number += 1
    return candidate


def _find_appearance(analysis: dict[str, Any], appearance_id: str) -> dict[str, Any]:
    for appearance in analysis.get("appearances", []):
        if appearance.get("appearance_id") == appearance_id:
            return appearance
    raise ValueError("El recurso no aparece en el análisis PDF")


def _find_family(analysis: dict[str, Any], family_id: str) -> dict[str, Any]:
    for family in analysis.get("proposed_groups", []):
        if family.get("group_id") == family_id:
            return family
    raise ValueError("La familia seleccionada no existe")


def _upsert(decisions: list[dict[str, Any]], decision: dict[str, Any]) -> None:
    for index, current in enumerate(decisions):
        if current.get("appearance_id") == decision.get("appearance_id"):
            decisions[index] = decision
            return
    decisions.append(decision)


def _log_change(project_dir, project_id, decision, previous) -> None:
    path = project_dir / "change_log.json"
    change_log = load_json(path)
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": decision.get("reviewed_at"),
            "actor": decision.get("reviewed_by"),
            "action": "resolve_resource_identity",
            "target_type": "resource_appearance",
            "target_id": decision.get("appearance_id"),
            "summary": f"Se resolvió identidad: {decision.get('action')}.",
            "before": previous,
            "after": decision,
        }
    )
    save_json(change_log, path)

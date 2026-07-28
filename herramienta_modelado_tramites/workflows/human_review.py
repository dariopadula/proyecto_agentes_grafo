from typing import Any

from config import LINK_ROLES
from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso


CONFIDENCE_VALUES = {"alta", "media", "baja"}


def save_link_decision(
    project_id: str,
    link_id: str,
    primary_role: str,
    secondary_roles: list[str],
    confidence: str,
    notes: str,
    actor: str,
) -> dict[str, Any]:
    """Guarda o actualiza la decision humana sobre un link candidato."""
    _validate_role(primary_role)
    for role in secondary_roles:
        _validate_role(role)
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError(
            f"Confianza invalida: {confidence}. Valores: {sorted(CONFIDENCE_VALUES)}"
        )

    project_dir = PROJECTS_DIR / project_id
    project_path = project_dir / "project.json"
    candidate_links_path = project_dir / "candidate_links.json"
    human_review_path = project_dir / "human_review.json"
    change_log_path = project_dir / "change_log.json"

    project = load_json(project_path)
    candidate_links = load_json(candidate_links_path)
    human_review = load_json(human_review_path)
    change_log = load_json(change_log_path)

    link = _find_link(candidate_links.get("links", []), link_id)
    previous_decision = _find_decision(human_review.get("decisions", []), link_id)
    timestamp = now_iso()

    decision = {
        "link_id": link_id,
        "url": link["url"],
        "primary_role": primary_role,
        "secondary_roles": _dedupe_roles(secondary_roles),
        "reviewed_by": actor,
        "reviewed_at": timestamp,
        "confidence": confidence,
        "notes": notes,
    }

    _upsert_decision(human_review, decision)
    human_review["review_status"] = _review_status(
        candidate_links.get("links", []),
        human_review.get("decisions", []),
    )
    human_review["updated_at"] = timestamp
    save_json(human_review, human_review_path)

    project["status"] = (
        "reviewed" if human_review["review_status"] == "complete" else "link_review"
    )
    project["updated_at"] = timestamp
    save_json(project, project_path)

    action = "classify_link" if previous_decision is None else "update_link_decision"
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "target_type": "candidate_link",
            "target_id": link_id,
            "summary": (
                f"Se guardo decision para {link_id}: "
                f"{primary_role} / {decision['secondary_roles']}."
            ),
            "before": previous_decision,
            "after": decision,
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "link_id": link_id,
        "primary_role": primary_role,
        "secondary_roles": decision["secondary_roles"],
        "review_status": human_review["review_status"],
        "human_review_path": str(human_review_path),
    }


def _validate_role(role: str) -> None:
    if role not in LINK_ROLES:
        raise ValueError(f"Rol invalido: {role}. Roles validos: {sorted(LINK_ROLES)}")


def _find_link(links: list[dict[str, Any]], link_id: str) -> dict[str, Any]:
    for link in links:
        if link.get("link_id") == link_id:
            return link
    raise ValueError(f"No existe link_id en candidate_links.json: {link_id}")


def _find_decision(
    decisions: list[dict[str, Any]],
    link_id: str,
) -> dict[str, Any] | None:
    for decision in decisions:
        if decision.get("link_id") == link_id:
            return dict(decision)
    return None


def _upsert_decision(
    human_review: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    decisions = human_review.setdefault("decisions", [])
    for index, current in enumerate(decisions):
        if current.get("link_id") == decision["link_id"]:
            decisions[index] = decision
            return
    decisions.append(decision)


def _review_status(
    links: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> str:
    reviewed_link_ids = {
        decision.get("link_id")
        for decision in decisions
        if decision.get("primary_role")
    }
    if links and all(link.get("link_id") in reviewed_link_ids for link in links):
        return "complete"
    if reviewed_link_ids:
        return "in_progress"
    return "not_started"


def _dedupe_roles(roles: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for role in roles:
        if role in seen:
            continue
        seen.add(role)
        deduped.append(role)
    return deduped

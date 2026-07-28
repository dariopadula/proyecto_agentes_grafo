from typing import Any

from config import PROJECTS_DIR
from core.internal_resource_extractor import extract_internal_resources
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso
from core.web_reader import fetch_page
from workflows.resource_filter_rules import apply_resource_filter_rules
from workflows.resource_filter_rules import load_or_create_resource_filter_rules


ACCEPTED_PRIMARY_ROLES = {
    "terminal_case",
    "auxiliary_info",
    "related_procedure",
    "shared_resource",
}


def discover_node_resources(project_id: str, actor: str) -> dict[str, Any]:
    """Explora links aceptados y guarda los recursos internos encontrados."""
    project_dir = PROJECTS_DIR / project_id
    project_path = project_dir / "project.json"
    candidate_links_path = project_dir / "candidate_links.json"
    human_review_path = project_dir / "human_review.json"
    node_resources_path = project_dir / "node_resources.json"
    change_log_path = project_dir / "change_log.json"

    project = load_json(project_path)
    candidate_links = load_json(candidate_links_path)
    human_review = load_json(human_review_path)
    change_log = load_json(change_log_path)
    resource_filter_rules = load_or_create_resource_filter_rules(project_id)
    timestamp = now_iso()

    decisions_by_link = {
        decision.get("link_id"): decision
        for decision in human_review.get("decisions", [])
    }
    accepted_links = [
        link
        for link in candidate_links.get("links", [])
        if _is_accepted(decisions_by_link.get(link.get("link_id"), {}))
    ]

    pages = []
    total_resources = 0
    total_discarded_resources = 0
    for link in accepted_links:
        page_result = _discover_one_page(link, resource_filter_rules)
        pages.append(page_result)
        total_resources += len(page_result.get("resources", []))
        total_discarded_resources += len(page_result.get("discarded_resources", []))

    payload = {
        "project_id": project_id,
        "generated_at": timestamp,
        "source": "accepted_candidate_links",
        "accepted_links_count": len(accepted_links),
        "resources_count": total_resources,
        "discarded_resources_count": total_discarded_resources,
        "filter_rules_path": str(project_dir / "resource_filter_rules.json"),
        "pages": pages,
    }
    save_json(payload, node_resources_path)

    project["status"] = "resource_discovery"
    project["updated_at"] = timestamp
    save_json(project, project_path)

    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "discover_node_resources",
            "target_type": "project",
            "target_id": project_id,
            "summary": (
                f"Se exploraron {len(accepted_links)} links aceptados y "
                f"se encontraron {total_resources} recursos internos utiles "
                f"y {total_discarded_resources} descartados por reglas."
            ),
            "before": None,
            "after": {
                "accepted_links_count": len(accepted_links),
                "resources_count": total_resources,
                "discarded_resources_count": total_discarded_resources,
            },
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "accepted_links_count": len(accepted_links),
        "resources_count": total_resources,
        "discarded_resources_count": total_discarded_resources,
        "node_resources_path": str(node_resources_path),
    }


def _discover_one_page(
    link: dict[str, Any],
    resource_filter_rules: dict[str, Any],
) -> dict[str, Any]:
    try:
        html = fetch_page(link["url"])
        extracted = extract_internal_resources(html, link["url"])
        resources, discarded_resources = apply_resource_filter_rules(
            extracted.get("resources", []),
            resource_filter_rules,
        )
        return {
            "link_id": link.get("link_id"),
            "url": link.get("url"),
            "title": link.get("title"),
            "status": "ok",
            "page_title": extracted.get("page_title", ""),
            "resources": resources,
            "discarded_resources": discarded_resources,
        }
    except Exception as error:
        return {
            "link_id": link.get("link_id"),
            "url": link.get("url"),
            "title": link.get("title"),
            "status": "error",
            "error": str(error),
            "resources": [],
            "discarded_resources": [],
        }


def _is_accepted(decision: dict[str, Any]) -> bool:
    primary_role = decision.get("primary_role")
    return primary_role in ACCEPTED_PRIMARY_ROLES

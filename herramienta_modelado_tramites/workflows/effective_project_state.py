from pathlib import Path
from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json


ACTIVE_NODE_ROLES = {
    "terminal_case",
    "auxiliary_info",
    "related_procedure",
    "shared_resource",
}


def resolve_effective_project_state(
    project_id: str,
    projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Construye una vista consolidada sin modificar los JSON del proyecto."""
    project_dir = (projects_dir or PROJECTS_DIR) / project_id
    candidate_links = _load_optional(project_dir / "candidate_links.json", {"links": []})
    human_review = _load_optional(project_dir / "human_review.json", {"decisions": []})
    node_resources = _load_optional(project_dir / "node_resources.json", {"pages": []})
    resource_review = _load_optional(project_dir / "resource_review.json", {"decisions": []})
    lifecycle_review = _load_optional(
        project_dir / "lifecycle_review.json",
        {"node_states": []},
    )

    decisions_by_link = {
        item.get("link_id"): item
        for item in human_review.get("decisions", [])
        if item.get("link_id")
    }
    lifecycle_by_link = {
        item.get("link_id"): item
        for item in lifecycle_review.get("node_states", [])
        if item.get("link_id")
    }
    pages_by_link = {
        item.get("link_id"): item
        for item in node_resources.get("pages", [])
        if item.get("link_id")
    }

    nodes = []
    active_node_ids = set()
    for candidate in candidate_links.get("links", []):
        link_id = candidate.get("link_id")
        decision = decisions_by_link.get(link_id, {})
        lifecycle = lifecycle_by_link.get(link_id, {})
        role = decision.get("primary_role")
        participates = role in ACTIVE_NODE_ROLES
        lifecycle_status = lifecycle.get("status", "active")
        is_active = participates and lifecycle_status == "active"
        if is_active:
            active_node_ids.add(link_id)
        nodes.append(
            {
                "link_id": link_id,
                "url": candidate.get("url"),
                "title": candidate.get("title"),
                "primary_role": role,
                "participates_in_model": participates,
                "lifecycle_status": lifecycle_status,
                "is_active": is_active,
                "resource_discovery_status": pages_by_link.get(link_id, {}).get("status"),
            }
        )

    resource_decisions = {
        item.get("decision_id"): item
        for item in resource_review.get("decisions", [])
        if item.get("decision_id")
    }
    appearances = []
    resources_by_key: dict[str, dict[str, Any]] = {}
    relations = []

    for page in node_resources.get("pages", []):
        link_id = page.get("link_id")
        for resource in page.get("resources", []):
            resource_id = resource.get("resource_id")
            appearance_id = f"{link_id}::{resource_id}"
            decision = resource_decisions.get(appearance_id)
            canonical_key = _canonical_key(appearance_id, decision)
            relation_active = link_id in active_node_ids
            appearance = {
                "appearance_id": appearance_id,
                "source_link_id": link_id,
                "resource_id": resource_id,
                "url": resource.get("url"),
                "title": resource.get("title"),
                "resource_type": resource.get("resource_type"),
                "decision_status": "decided" if decision and decision.get("use") else "pending",
                "decision_source": decision.get("decision_source") if decision else None,
                "effective_use": decision.get("use") if decision else None,
                "canonical_resource_key": canonical_key,
                "relation_active": relation_active,
            }
            appearances.append(appearance)
            relations.append(
                {
                    "relation_id": appearance_id,
                    "source_link_id": link_id,
                    "canonical_resource_key": canonical_key,
                    "appearance_id": appearance_id,
                    "status": "active" if relation_active else "inactive",
                }
            )
            canonical = resources_by_key.setdefault(
                canonical_key,
                {
                    "canonical_resource_key": canonical_key,
                    "canonical_url": _canonical_url(resource, decision),
                    "display_name": (decision or {}).get("title") or resource.get("title"),
                    "resource_type": (decision or {}).get("resource_type") or resource.get("resource_type"),
                    "appearance_ids": [],
                    "active_source_link_ids": set(),
                    "uses": set(),
                    "decision_sources": set(),
                },
            )
            canonical["appearance_ids"].append(appearance_id)
            if relation_active:
                canonical["active_source_link_ids"].add(link_id)
            if decision and decision.get("use"):
                canonical["uses"].add(decision["use"])
            if decision and decision.get("decision_source"):
                canonical["decision_sources"].add(decision["decision_source"])

    canonical_resources = []
    inconsistencies = []
    for canonical in resources_by_key.values():
        active_sources = sorted(canonical.pop("active_source_link_ids"))
        uses = sorted(canonical.pop("uses"))
        decision_sources = sorted(canonical.pop("decision_sources"))
        canonical["active_source_link_ids"] = active_sources
        canonical["effective_scope"] = _scope_for(active_sources)
        canonical["lifecycle_status"] = "active" if active_sources else "orphaned"
        canonical["effective_use"] = uses[0] if len(uses) == 1 else None
        canonical["decision_sources"] = decision_sources
        canonical["has_conflicting_uses"] = len(uses) > 1
        if len(uses) > 1:
            inconsistencies.append(
                {
                    "type": "conflicting_resource_uses",
                    "canonical_resource_key": canonical["canonical_resource_key"],
                    "values": uses,
                }
            )
        canonical_resources.append(canonical)

    return {
        "schema_version": "0.1",
        "project_id": project_id,
        "source": "calculated_from_project_decisions",
        "nodes": nodes,
        "appearances": appearances,
        "canonical_resources": canonical_resources,
        "relations": relations,
        "inconsistencies": inconsistencies,
        "summary": {
            "node_count": len(nodes),
            "active_node_count": len(active_node_ids),
            "appearance_count": len(appearances),
            "canonical_resource_count": len(canonical_resources),
            "active_relation_count": sum(item["status"] == "active" for item in relations),
            "pending_appearance_count": sum(
                item["decision_status"] == "pending" for item in appearances
            ),
            "orphaned_resource_count": sum(
                item["lifecycle_status"] == "orphaned" for item in canonical_resources
            ),
            "inconsistency_count": len(inconsistencies),
        },
    }


def _canonical_key(
    appearance_id: str,
    decision: dict[str, Any] | None,
) -> str:
    if not decision:
        return f"appearance:{appearance_id}"
    if decision.get("canonical_resource_id"):
        return f"canonical:{decision['canonical_resource_id']}"
    if decision.get("source_group_id") and decision.get("canonical_url"):
        return f"group:{decision['source_group_id']}"
    return f"appearance:{appearance_id}"


def _canonical_url(
    resource: dict[str, Any],
    decision: dict[str, Any] | None,
) -> str | None:
    return (decision or {}).get("canonical_url") or resource.get("url")


def _scope_for(active_source_ids: list[str]) -> str:
    if not active_source_ids:
        return "orphaned"
    if len(active_source_ids) == 1:
        return "node_only"
    return "shared"


def _load_optional(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    return load_json(path) if path.exists() else default

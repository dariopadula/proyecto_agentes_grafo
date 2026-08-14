from collections import defaultdict
from typing import Any


DOCUMENT_RESOURCE_TYPES = {"pdf", "formulario"}


def build_document_map(state: dict[str, Any]) -> dict[str, Any]:
    """Proyecta el estado efectivo para una visualización documental de solo lectura."""
    nodes_by_id = {
        item.get("link_id"): item
        for item in state.get("nodes", [])
        if item.get("link_id")
    }
    appearances_by_id = {
        item.get("appearance_id"): item
        for item in state.get("appearances", [])
        if item.get("appearance_id")
    }
    canonical_by_key = {
        item.get("canonical_resource_key"): item
        for item in state.get("canonical_resources", [])
        if item.get("canonical_resource_key")
    }

    relations_by_node: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    source_ids_by_resource: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"active": set(), "inactive": set()}
    )
    for relation in state.get("relations", []):
        node_id = relation.get("source_link_id")
        resource_key = relation.get("canonical_resource_key")
        if not node_id or not resource_key:
            continue
        relations_by_node[node_id][resource_key].append(relation)
        status = relation.get("status", "inactive")
        source_ids_by_resource[resource_key][status].add(node_id)

    resources = {}
    for resource_key, canonical in canonical_by_key.items():
        resources[resource_key] = _resource_projection(
            canonical,
            source_ids_by_resource[resource_key],
            appearances_by_id,
            nodes_by_id,
        )

    nodes = []
    for node in state.get("nodes", []):
        if node.get("primary_role") != "terminal_case":
            continue
        node_id = node.get("link_id")
        node_resources = []
        for resource_key, relations in relations_by_node.get(node_id, {}).items():
            resource = resources.get(resource_key)
            if not resource:
                continue
            item = dict(resource)
            item["relation_status"] = (
                "active"
                if any(relation.get("status") == "active" for relation in relations)
                else "inactive"
            )
            item["node_appearance_ids"] = sorted(
                relation.get("appearance_id")
                for relation in relations
                if relation.get("appearance_id")
            )
            item["node_appearances"] = sorted(
                (
                    {
                        "appearance_id": appearance_id,
                        "source_link_id": appearances_by_id[appearance_id].get("source_link_id"),
                        "resource_id": appearances_by_id[appearance_id].get("resource_id"),
                        "title": appearances_by_id[appearance_id].get("title"),
                        "url": appearances_by_id[appearance_id].get("url"),
                        "effective_use": appearances_by_id[appearance_id].get("effective_use"),
                        "decision_source": appearances_by_id[appearance_id].get("decision_source"),
                    }
                    for appearance_id in item["node_appearance_ids"]
                    if appearance_id in appearances_by_id
                ),
                key=lambda appearance: appearance.get("appearance_id", ""),
            )
            node_uses = {
                appearance.get("effective_use")
                for appearance in item["node_appearances"]
                if appearance.get("effective_use")
            }
            item["effective_use"] = next(iter(node_uses)) if len(node_uses) == 1 else None
            item["has_conflicting_uses"] = len(node_uses) > 1
            node_resources.append(item)
        node_resources.sort(key=_resource_sort_key)
        nodes.append(
            {
                "link_id": node_id,
                "title": node.get("title") or node_id,
                "url": node.get("url"),
                "is_active": bool(node.get("is_active")),
                "lifecycle_status": node.get("lifecycle_status"),
                "resource_discovery_status": node.get("resource_discovery_status"),
                "resources": node_resources,
                "summary": _node_summary(node_resources),
            }
        )

    nodes.sort(key=lambda item: (not item["is_active"], item["title"].lower()))
    shared_resources = sorted(
        (
            item
            for item in resources.values()
            if len(item["active_source_nodes"]) > 1
        ),
        key=_resource_sort_key,
    )
    return {
        "schema_version": "0.1",
        "project_id": state.get("project_id"),
        "nodes": nodes,
        "resources": resources,
        "shared_resources": shared_resources,
        "summary": {
            "terminal_node_count": len(nodes),
            "active_terminal_node_count": sum(item["is_active"] for item in nodes),
            "shared_resource_count": len(shared_resources),
            "resource_count": len(resources),
        },
    }


def _resource_projection(
    canonical: dict[str, Any],
    source_ids: dict[str, set[str]],
    appearances_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    resource_key = canonical.get("canonical_resource_key", "")
    appearance_ids = canonical.get("appearance_ids", [])
    appearance_sources = [
        appearances_by_id[item]
        for item in appearance_ids
        if item in appearances_by_id
    ]
    return {
        "canonical_resource_key": resource_key,
        "display_name": canonical.get("display_name") or canonical.get("canonical_url") or resource_key,
        "canonical_url": canonical.get("canonical_url"),
        "resource_type": canonical.get("resource_type") or "sin_tipo",
        "effective_use": canonical.get("effective_use"),
        "effective_scope": canonical.get("effective_scope"),
        "lifecycle_status": canonical.get("lifecycle_status"),
        "is_consolidated": not resource_key.startswith("appearance:"),
        "has_conflicting_uses": bool(canonical.get("has_conflicting_uses")),
        "appearance_ids": list(appearance_ids),
        "appearance_count": len(appearance_ids),
        "appearance_sources": [
            {
                "appearance_id": item.get("appearance_id"),
                "source_link_id": item.get("source_link_id"),
                "title": item.get("title"),
                "url": item.get("url"),
            }
            for item in appearance_sources
        ],
        "active_source_nodes": _source_nodes(source_ids["active"], nodes_by_id),
        "inactive_source_nodes": _source_nodes(source_ids["inactive"], nodes_by_id),
    }


def _source_nodes(
    source_ids: set[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "link_id": source_id,
                "title": nodes_by_id.get(source_id, {}).get("title") or source_id,
            }
            for source_id in source_ids
        ),
        key=lambda item: item["title"].lower(),
    )


def _node_summary(resources: list[dict[str, Any]]) -> dict[str, int]:
    active = [item for item in resources if item["relation_status"] == "active"]
    deliverable = [item for item in active if item.get("effective_use") != "discard"]
    return {
        "resource_count": len(active),
        "context_count": sum(item.get("effective_use") == "process_as_context" for item in active),
        "link_count": sum(item.get("effective_use") == "show_as_link" for item in active),
        "discarded_count": sum(item.get("effective_use") == "discard" for item in active),
        "pending_count": sum(not item.get("effective_use") for item in active),
        "shared_count": sum(len(item.get("active_source_nodes", [])) > 1 for item in deliverable),
        "consolidated_count": sum(item.get("is_consolidated") for item in deliverable),
        "provisional_count": sum(not item.get("is_consolidated") for item in deliverable),
        "document_count": sum(item.get("resource_type") in DOCUMENT_RESOURCE_TYPES for item in deliverable),
        "auxiliary_link_count": sum(item.get("resource_type") not in DOCUMENT_RESOURCE_TYPES for item in deliverable),
    }


def _resource_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    use_order = {
        "process_as_context": 0,
        "show_as_link": 1,
        None: 2,
        "review_later": 2,
        "discard": 3,
    }
    return (
        use_order.get(item.get("effective_use"), 2),
        item.get("resource_type", ""),
        item.get("display_name", "").lower(),
    )

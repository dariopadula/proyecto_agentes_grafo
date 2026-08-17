from collections import Counter
from collections import defaultdict
from typing import Any

from config import AUXILIARY_LINK_MAX_REDIRECTS
from config import AUXILIARY_LINK_REDIRECT_TIMEOUT_SECONDS
from config import PROJECTS_DIR
from core.internal_resource_extractor import ALLOWED_RESOURCE_DOMAINS
from core.json_store import load_json
from core.json_store import save_json
from core.redirect_resolver import resolve_redirect_chain
from core.time_utils import now_iso
from core.url_normalizer import analyze_url


def analyze_auxiliary_links(project_id: str, actor: str) -> dict[str, Any]:
    """Inventaría enlaces no documentales y propone grupos revisables."""
    project_dir = PROJECTS_DIR / project_id
    node_resources_path = project_dir / "node_resources.json"
    resource_review_path = project_dir / "resource_review.json"
    analysis_path = project_dir / "auxiliary_link_analysis.json"
    change_log_path = project_dir / "change_log.json"

    node_resources = load_json(node_resources_path)
    resource_review = load_json(resource_review_path)
    change_log = load_json(change_log_path)
    timestamp = now_iso()
    existing_analysis = (
        load_json(analysis_path)
        if analysis_path.exists()
        else {}
    )

    decisions = {
        decision.get("decision_id"): decision
        for decision in resource_review.get("decisions", [])
    }
    appearances, excluded_documents = _build_appearances(
        node_resources,
        decisions,
    )
    _resolve_intermediate_agendas(appearances)
    exact_groups = _build_groups(
        appearances,
        key_field="detected_url",
        prefix="exact_url",
        certainty="exact_url",
        evidence_field="detected_url",
        existing_groups=existing_analysis.get("exact_url_groups", []),
    )
    normalized_groups = _build_groups(
        appearances,
        key_field="identity_key",
        prefix="normalized_url",
        certainty="strong_normalized_equivalent",
        evidence_field="identity_key",
        require_distinct_urls=True,
        existing_groups=existing_analysis.get(
            "normalized_equivalence_candidates", []
        ),
    )
    agenda_groups = _build_groups(
        [
            appearance
            for appearance in appearances
            if appearance.get("functional_kind") == "agenda"
        ],
        key_field="identity_key",
        prefix="agenda",
        certainty="agenda_parameters_match",
        evidence_field="identity_key",
        include_singletons=True,
        existing_groups=existing_analysis.get("agenda_candidates", []),
    )

    payload = {
        "schema_version": "0.1",
        "generated_at": timestamp,
        "project_id": project_id,
        "resource_scope": "non_document_auxiliary_links",
        "source": {
            "node_resources": str(node_resources_path),
            "resource_review": str(resource_review_path),
        },
        "analysis_policy": {
            "semantic_interpretation": False,
            "llm_usage": False,
            "redirect_resolution": {
                "enabled_for_intermediate_agendas": True,
                "follows_html_links": False,
                "max_redirects": AUXILIARY_LINK_MAX_REDIRECTS,
                "allowed_hosts": sorted(ALLOWED_RESOURCE_DOMAINS),
            },
            "persists_human_decisions": False,
            "agenda_identity_fields": [
                "host",
                "path",
                "agenda",
                "recurso",
            ],
            "agenda_evidence_only_parameters": [
                "pagina_retorno",
                "solo_cuerpo",
            ],
        },
        "summary": _summary(
            appearances,
            excluded_documents,
            exact_groups,
            normalized_groups,
            agenda_groups,
        ),
        "appearances": appearances,
        "excluded_documents": excluded_documents,
        "exact_url_groups": exact_groups,
        "normalized_equivalence_candidates": normalized_groups,
        "agenda_candidates": agenda_groups,
        "review_questions": _review_questions(
            appearances,
            normalized_groups,
        ),
    }
    save_json(payload, analysis_path)

    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "analyze_auxiliary_links",
            "target_type": "project",
            "target_id": project_id,
            "summary": (
                f"Se inventariaron {len(appearances)} apariciones de enlaces "
                f"auxiliares no documentales y {len(agenda_groups)} agendas "
                "candidatas."
            ),
            "before": None,
            "after": payload["summary"],
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "appearance_count": len(appearances),
        "excluded_document_count": len(excluded_documents),
        "exact_group_count": len(exact_groups),
        "normalized_group_count": len(normalized_groups),
        "agenda_group_count": len(agenda_groups),
        "analysis_path": str(analysis_path),
    }


def _build_appearances(
    node_resources: dict[str, Any],
    decisions: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    appearances = []
    excluded_documents = []

    for page in node_resources.get("pages", []):
        for collection, filter_status in (
            ("resources", "reviewable"),
            ("discarded_resources", "discarded_by_rule"),
        ):
            for resource in page.get(collection, []):
                appearance_id = (
                    f"{page.get('link_id')}::{resource.get('resource_id')}"
                )
                decision = decisions.get(appearance_id, {})
                url_evidence = analyze_url(
                    resource.get("url", ""),
                    resource.get("resource_type", ""),
                )
                item = {
                    "appearance_id": appearance_id,
                    "source_node_id": page.get("link_id"),
                    "source_node_title": page.get("title", ""),
                    "resource_id": resource.get("resource_id"),
                    "label": resource.get("title", ""),
                    "anchor_text": resource.get("anchor_text", ""),
                    "source_context": resource.get("source_context", ""),
                    "detected_url": resource.get("url", ""),
                    "detected_resource_type": resource.get(
                        "resource_type",
                        "",
                    ),
                    "filter_status": filter_status,
                    "discard_rule_id": resource.get("discard_rule_id"),
                    "discard_reason": resource.get("discard_reason"),
                    "existing_use": decision.get("use"),
                    "existing_scope": decision.get("scope"),
                    **url_evidence,
                }
                if item["is_document"]:
                    excluded_documents.append(item)
                else:
                    appearances.append(item)

    sort_key = lambda item: (
        item.get("source_node_id", ""),
        item.get("resource_id", ""),
    )
    return sorted(appearances, key=sort_key), sorted(
        excluded_documents,
        key=sort_key,
    )


def _resolve_intermediate_agendas(
    appearances: list[dict[str, Any]],
    resolver=resolve_redirect_chain,
) -> None:
    for item in appearances:
        if item.get("functional_kind") != "agenda":
            continue
        if set(item.get("identity_parameters", {})) == {
            "agenda",
            "recurso",
        }:
            item["redirect_resolution"] = {
                "status": "not_needed",
                "original_url": item.get("detected_url"),
                "final_url": item.get("detected_url"),
                "redirect_count": 0,
                "chain": [item.get("detected_url")],
                "error": None,
            }
            item["candidate_canonical_url"] = item.get("detected_url")
            continue

        resolution = resolver(
            item.get("detected_url", ""),
            allowed_hosts=ALLOWED_RESOURCE_DOMAINS,
            max_redirects=AUXILIARY_LINK_MAX_REDIRECTS,
            timeout_seconds=AUXILIARY_LINK_REDIRECT_TIMEOUT_SECONDS,
        )
        item["redirect_resolution"] = resolution
        final_url = resolution.get("final_url", "")
        if resolution.get("status") != "resolved" or not final_url:
            item["candidate_canonical_url"] = item.get("detected_url")
            continue

        original_identity_key = item.get("identity_key")
        item.update(analyze_url(final_url, "agenda"))
        item["original_identity_key"] = original_identity_key
        item["candidate_canonical_url"] = final_url


def _build_groups(
    appearances: list[dict[str, Any]],
    key_field: str,
    prefix: str,
    certainty: str,
    evidence_field: str,
    require_distinct_urls: bool = False,
    include_singletons: bool = False,
    existing_groups: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for appearance in appearances:
        value = appearance.get(key_field, "")
        if value:
            buckets[value].append(appearance)

    groups = []
    existing_ids = {
        group.get("evidence", {}).get("value"): group.get("group_id")
        for group in (existing_groups or [])
        if group.get("group_id")
    }
    used_numbers = []
    for group_id in existing_ids.values():
        suffix = str(group_id).rsplit("_", 1)[-1]
        if suffix.isdigit():
            used_numbers.append(int(suffix))
    next_number = max(used_numbers, default=0) + 1
    for value, items in sorted(buckets.items()):
        urls = sorted({item.get("detected_url", "") for item in items})
        if not include_singletons and len(items) < 2:
            continue
        if require_distinct_urls and len(urls) < 2:
            continue
        group_id = existing_ids.get(value)
        if not group_id:
            group_id = f"{prefix}_{next_number:03d}"
            next_number += 1
        groups.append(
            {
                "group_id": group_id,
                "certainty": certainty,
                "evidence": {
                    "field": evidence_field,
                    "value": value,
                    "appearance_count": len(items),
                    "distinct_url_count": len(urls),
                },
                "appearance_ids": [
                    item["appearance_id"] for item in items
                ],
                "source_node_ids": sorted(
                    {item.get("source_node_id", "") for item in items}
                ),
                "detected_urls": urls,
                "candidate_canonical_urls": sorted(
                    {
                        item.get("candidate_canonical_url")
                        or item.get("detected_url", "")
                        for item in items
                    }
                ),
                "suggested_functional_kind": _single_or_mixed(
                    item.get("functional_kind", "") for item in items
                ),
                "existing_uses": sorted(
                    {
                        item.get("existing_use")
                        for item in items
                        if item.get("existing_use")
                    }
                ),
                "review_status": "pending_human_confirmation",
            }
        )
    return groups


def _summary(
    appearances: list[dict[str, Any]],
    excluded_documents: list[dict[str, Any]],
    exact_groups: list[dict[str, Any]],
    normalized_groups: list[dict[str, Any]],
    agenda_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "appearance_count": len(appearances),
        "excluded_document_count": len(excluded_documents),
        "by_functional_kind": dict(
            sorted(
                Counter(
                    item.get("functional_kind", "desconocido")
                    for item in appearances
                ).items()
            )
        ),
        "by_existing_use": dict(
            sorted(
                Counter(
                    item.get("existing_use") or "sin_decision"
                    for item in appearances
                ).items()
            )
        ),
        "by_filter_status": dict(
            sorted(
                Counter(
                    item.get("filter_status", "")
                    for item in appearances
                ).items()
            )
        ),
        "exact_url_group_count": len(exact_groups),
        "normalized_equivalence_candidate_count": len(normalized_groups),
        "agenda_candidate_count": len(agenda_groups),
        "agenda_repeated_candidate_count": sum(
            group["evidence"]["appearance_count"] > 1
            for group in agenda_groups
        ),
        "representative_examples": {
            "process_as_context": _example_ids(
                appearances,
                lambda item: item.get("existing_use")
                == "process_as_context",
            ),
            "show_as_link": _example_ids(
                appearances,
                lambda item: item.get("existing_use") == "show_as_link",
            ),
            "discarded_by_rule": _example_ids(
                appearances,
                lambda item: item.get("filter_status")
                == "discarded_by_rule",
            ),
            "needs_review": _example_ids(
                appearances,
                lambda item: not item.get("existing_use")
                and item.get("filter_status") == "reviewable",
            ),
        },
    }


def _review_questions(
    appearances: list[dict[str, Any]],
    normalized_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    questions = []
    schemes_by_identity: dict[str, set[str]] = defaultdict(set)
    for item in appearances:
        schemes_by_identity[item.get("identity_key", "")].add(
            item.get("scheme", "")
        )
    mixed_scheme_keys = sorted(
        key
        for key, schemes in schemes_by_identity.items()
        if key and len(schemes) > 1
    )
    if mixed_scheme_keys:
        questions.append(
            {
                "question": (
                    "¿HTTP y HTTPS deben considerarse el mismo destino "
                    "candidato?"
                ),
                "affected_identity_keys": mixed_scheme_keys,
            }
        )

    if normalized_groups:
        questions.append(
            {
                "question": (
                    "¿Las equivalencias obtenidas solo por codificación u "
                    "orden de parámetros pueden proponerse con certeza alta?"
                ),
                "affected_group_ids": [
                    group["group_id"] for group in normalized_groups
                ],
            }
        )

    unusual_agendas = [
        {
            "appearance_id": item.get("appearance_id"),
            "missing_identity_parameters": sorted(
                {
                    "agenda",
                    "recurso",
                }
                - set(item.get("identity_parameters", {}))
            ),
            "unexpected_parameters": item.get(
                "unexpected_parameters",
                {},
            ),
        }
        for item in appearances
        if item.get("functional_kind") == "agenda"
        and (
            set(item.get("identity_parameters", {}))
            != {"agenda", "recurso"}
            or item.get("unexpected_parameters")
        )
    ]
    if unusual_agendas:
        questions.append(
            {
                "question": (
                    "¿Cómo deben tratarse las agendas sin los parámetros "
                    "agenda/recurso o con parámetros no previstos?"
                ),
                "affected_appearances": unusual_agendas,
            }
        )
    return questions


def _single_or_mixed(values) -> str:
    unique = sorted({value for value in values if value})
    if len(unique) == 1:
        return unique[0]
    return "mixed" if unique else "desconocido"


def _example_ids(appearances, predicate, limit: int = 5) -> list[str]:
    return [
        item["appearance_id"]
        for item in appearances
        if predicate(item)
    ][:limit]

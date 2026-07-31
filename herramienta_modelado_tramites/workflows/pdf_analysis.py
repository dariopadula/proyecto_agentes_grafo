import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlparse

import requests

from config import PDF_DOWNLOAD_TIMEOUT_SECONDS
from config import PDF_MAX_DOWNLOAD_BYTES
from config import PDF_MAX_TEXT_CHARACTERS
from config import PDF_MAX_TEXT_PAGES
from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.pdf_analyzer import analyze_pdf_content
from core.time_utils import now_iso
from workflows.resource_identity_review import apply_pdf_membership_decisions


DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-UY,es;q=0.9,en;q=0.7",
}


class PdfVerificationSkipped(Exception):
    """El PDF excede una política de seguridad, sin considerarse un error."""


def analyze_project_pdfs(
    project_id: str,
    actor: str,
) -> dict[str, Any]:
    """Analiza PDF revisados y genera propuestas sin guardar decisiones humanas."""
    project_dir = PROJECTS_DIR / project_id
    node_resources_path = project_dir / "node_resources.json"
    resource_review_path = project_dir / "resource_review.json"
    pdf_analysis_path = project_dir / "pdf_analysis.json"
    change_log_path = project_dir / "change_log.json"
    local_pdf_dir = project_dir / "pdfs"

    node_resources = load_json(node_resources_path)
    resource_review = load_json(resource_review_path)
    change_log = load_json(change_log_path)
    timestamp = now_iso()

    candidates = _pdf_candidates(node_resources, resource_review)
    appearances = [
        _candidate_appearance(candidate)
        for candidate in candidates
    ]
    existing_analysis = (
        load_json(pdf_analysis_path)
        if pdf_analysis_path.exists()
        else {"proposed_groups": []}
    )
    proposed_groups = _build_pdf_families(appearances, existing_analysis)
    identity_review_path = project_dir / "resource_identity_review.json"

    payload = {
        "schema_version": "0.1",
        "generated_at": timestamp,
        "project_id": project_id,
        "resource_type": "pdf",
        "source": {
            "node_resources": str(node_resources_path),
            "resource_review": str(resource_review_path),
            "local_pdf_dir": str(local_pdf_dir),
        },
        "analysis_policy": {
            "semantic_interpretation": False,
            "llm_usage": False,
            "candidate_source": "all_included_pdf_resources",
            "verification_mode": "on_demand_by_family",
        },
        "summary": _analysis_summary(appearances, proposed_groups),
        "appearances": appearances,
        "proposed_groups": proposed_groups,
    }
    if identity_review_path.exists():
        payload = apply_pdf_membership_decisions(
            payload,
            load_json(identity_review_path),
        )
        payload["summary"] = _analysis_summary(
            payload.get("appearances", []),
            payload.get("proposed_groups", []),
        )
    save_json(payload, pdf_analysis_path)

    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "analyze_pdf_resources",
            "target_type": "project",
            "target_id": project_id,
            "summary": (
                f"Se prepararon {len(appearances)} apariciones de PDF y "
                f"se propusieron {len(proposed_groups)} familias por nombre."
            ),
            "before": None,
            "after": payload["summary"],
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "appearance_count": len(appearances),
        "analyzed_count": payload["summary"]["analyzed_count"],
        "error_count": payload["summary"]["error_count"],
        "not_attempted_count": payload["summary"]["not_attempted_count"],
        "proposed_group_count": len(proposed_groups),
        "pdf_analysis_path": str(pdf_analysis_path),
    }


def verify_pdf_family(
    project_id: str,
    family_id: str,
    actor: str,
    local_only: bool = False,
) -> dict[str, Any]:
    """Descarga y particiona por contenido una única familia propuesta."""
    project_dir = PROJECTS_DIR / project_id
    analysis_path = project_dir / "pdf_analysis.json"
    change_log_path = project_dir / "change_log.json"
    local_pdf_dir = project_dir / "pdfs"
    payload = load_json(analysis_path)
    change_log = load_json(change_log_path)
    family = _find_family(payload, family_id)
    appearance_ids = set(family.get("appearance_ids", []))
    local_files = _index_local_pdfs(local_pdf_dir)

    updated = []
    for appearance in payload.get("appearances", []):
        if appearance.get("appearance_id") not in appearance_ids:
            continue
        analyzed = _analyze_existing_appearance(
            appearance,
            local_files,
            local_only,
        )
        appearance.clear()
        appearance.update(analyzed)
        updated.append(appearance)

    family["verification"] = _build_verification(family_id, updated)
    payload["generated_at"] = now_iso()
    payload["summary"] = _analysis_summary(
        payload.get("appearances", []),
        payload.get("proposed_groups", []),
    )
    save_json(payload, analysis_path)

    timestamp = now_iso()
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "verify_pdf_family",
            "target_type": "pdf_family",
            "target_id": family_id,
            "summary": (
                f"Se verificó la familia {family_id}: "
                f"{len(family['verification']['partitions'])} particiones y "
                f"{len(family['verification']['unverified_appearance_ids'])} "
                "apariciones no verificadas."
            ),
            "before": None,
            "after": family["verification"],
        }
    )
    save_json(change_log, change_log_path)
    _reconcile_manual_family_decision(project_dir, family)
    return family["verification"]


def mark_pdf_family_verification_queued(
    project_id: str,
    family_id: str,
) -> None:
    """Deja visible que la verificación automática se ejecutará en segundo plano."""
    analysis_path = PROJECTS_DIR / project_id / "pdf_analysis.json"
    payload = load_json(analysis_path)
    family = _find_family(payload, family_id)
    family["verification"]["status"] = "queued"
    save_json(payload, analysis_path)


def mark_pdf_family_verification_failed(
    project_id: str,
    family_id: str,
    error: Exception,
) -> None:
    """Evita que una falla inesperada deje la familia eternamente en cola."""
    analysis_path = PROJECTS_DIR / project_id / "pdf_analysis.json"
    payload = load_json(analysis_path)
    family = _find_family(payload, family_id)
    family["verification"].update(
        {
            "status": "error",
            "verified_at": now_iso(),
            "error": f"{type(error).__name__}: {error}",
        }
    )
    save_json(payload, analysis_path)


def _reconcile_manual_family_decision(
    project_dir: Path,
    family: dict[str, Any],
) -> None:
    review_path = project_dir / "pdf_group_review.json"
    if not review_path.exists():
        return
    review = load_json(review_path)
    changed = False
    inherited_partition = None
    verification = family.get("verification", {})
    for decision in review.get("family_decisions", []):
        if decision.get("family_id") != family.get("group_id"):
            continue
        if verification.get("status") != "complete":
            result = "verification_incomplete"
        elif verification.get("all_appearances_same"):
            result = "consistent"
        else:
            result = "conflict"
        decision["verification_reconciliation"] = result
        if result == "consistent":
            partition = verification.get("partitions", [])[0]
            partition_id = partition.get("partition_id")
            existing = next(
                (
                    item
                    for item in review.get("decisions", [])
                    if item.get("partition_id") == partition_id
                ),
                None,
            )
            if existing is None:
                inherited_partition = {
                    "family_id": family.get("group_id"),
                    "partition_id": partition_id,
                    "identity_decision": "confirmed_same",
                    "default_use": decision.get("default_use"),
                    "selected_canonical_url": decision.get(
                        "selected_canonical_url"
                    ),
                    "display_name": decision.get("display_name"),
                    "notes": decision.get("notes"),
                    "reviewed_by": decision.get("reviewed_by"),
                    "reviewed_at": decision.get("reviewed_at"),
                    "analysis_generated_at": now_iso(),
                    "decision_source": "inherited_from_family",
                    "inherited_at": now_iso(),
                }
                review.setdefault("decisions", []).append(inherited_partition)
        changed = True
    if changed:
        review["updated_at"] = now_iso()
        save_json(review, review_path)
    if inherited_partition is not None:
        change_log_path = project_dir / "change_log.json"
        change_log = load_json(change_log_path)
        change_log["events"].append(
            {
                "event_id": f"event_{len(change_log['events']) + 1:03d}",
                "timestamp": now_iso(),
                "actor": inherited_partition.get("reviewed_by"),
                "action": "inherit_pdf_family_decision",
                "target_type": "pdf_partition",
                "target_id": inherited_partition.get("partition_id"),
                "summary": (
                    "La verificación produjo una sola partición y se aplicó "
                    "automáticamente la decisión familiar."
                ),
                "before": None,
                "after": inherited_partition,
            }
        )
        save_json(change_log, change_log_path)


def _pdf_candidates(
    node_resources: dict[str, Any],
    resource_review: dict[str, Any],
) -> list[dict[str, Any]]:
    """Incluye todos los PDF no excluidos, aunque sigan sin revisión individual."""
    decisions = {
        (
            item.get("source_link_id"),
            item.get("resource_id"),
        ): item
        for item in resource_review.get("decisions", [])
    }
    candidates = []
    for page in node_resources.get("pages", []):
        source_link_id = page.get("link_id")
        for resource in page.get("resources", []):
            if resource.get("resource_type") != "pdf":
                continue
            decision = decisions.get(
                (source_link_id, resource.get("resource_id")),
                {},
            )
            candidates.append(
                {
                    "appearance_id": (
                        f"{source_link_id}::{resource.get('resource_id')}"
                    ),
                    "source_node_id": source_link_id,
                    "source_node_title": page.get("title", ""),
                    "resource_id": resource.get("resource_id"),
                    "label": resource.get("title", ""),
                    "detected_url": resource.get("url", ""),
                    "existing_use": decision.get("use"),
                    "existing_scope": decision.get("scope"),
                }
            )

    return sorted(
        candidates,
        key=lambda item: (
            item.get("source_node_id", ""),
            item.get("resource_id", ""),
        ),
    )


def _index_local_pdfs(local_pdf_dir: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    if not local_pdf_dir.exists():
        return index

    for path in sorted(local_pdf_dir.glob("*.pdf")):
        index[_local_match_name(path.name)].append(path)
    return index


def _candidate_appearance(candidate: dict[str, Any]) -> dict[str, Any]:
    file_name = _file_name(candidate.get("detected_url", ""))
    return {
        **candidate,
        "file_name": file_name,
        "canonical_name": _canonical_pdf_name(file_name),
        "analysis": _empty_analysis("not_verified"),
    }


def _analyze_existing_appearance(
    appearance: dict[str, Any],
    local_files: dict[str, list[Path]],
    local_only: bool,
) -> dict[str, Any]:
    file_name = appearance.get("file_name", "")
    local_path = _take_local_file(local_files, file_name)
    result = {**appearance, "analysis": _empty_analysis("pending")}

    try:
        if local_path is not None:
            content = local_path.read_bytes()
            source = "local_file"
            local_file_name = local_path.name
        elif local_only:
            result["analysis"]["status"] = "not_attempted_local_only"
            return result
        else:
            content = _download_pdf(appearance.get("detected_url", ""))
            source = "download"
            local_file_name = None

        if len(content) > PDF_MAX_DOWNLOAD_BYTES:
            raise PdfVerificationSkipped(
                f"El archivo supera el límite de "
                f"{PDF_MAX_DOWNLOAD_BYTES} bytes."
            )
        metrics = analyze_pdf_content(
            content,
            max_text_pages=PDF_MAX_TEXT_PAGES,
            max_text_characters=PDF_MAX_TEXT_CHARACTERS,
        )
        result["analysis"].update(
            {
                "status": "analyzed",
                "source": source,
                "local_file_name": local_file_name,
                **metrics,
            }
        )
    except PdfVerificationSkipped as error:
        result["analysis"]["status"] = "skipped_by_policy"
        result["analysis"]["error"] = str(error)
    except requests.RequestException as error:
        result["analysis"]["status"] = "download_error"
        result["analysis"]["error"] = f"{type(error).__name__}: {error}"
    except Exception as error:
        result["analysis"]["status"] = "analysis_error"
        result["analysis"]["error"] = f"{type(error).__name__}: {error}"

    return result


def _empty_analysis(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "source": None,
        "local_file_name": None,
        "size_bytes": None,
        "page_count": None,
        "character_count": 0,
        "word_count": 0,
        "binary_sha256": "",
        "normalized_text_sha256": "",
        "encrypted": None,
        "text_extraction_truncated": False,
        "error": None,
    }


def _download_pdf(url: str) -> bytes:
    parsed = urlparse(url)
    headers = {
        **DOWNLOAD_HEADERS,
        "Referer": f"{parsed.scheme}://{parsed.netloc}/",
    }
    response = requests.get(
        url,
        timeout=(5, PDF_DOWNLOAD_TIMEOUT_SECONDS),
        headers=headers,
        stream=True,
    )
    response.raise_for_status()
    declared_size = int(response.headers.get("Content-Length", "0") or 0)
    if declared_size > PDF_MAX_DOWNLOAD_BYTES:
        raise PdfVerificationSkipped(
            f"Tamaño informado {declared_size} bytes; "
            f"límite {PDF_MAX_DOWNLOAD_BYTES} bytes."
        )
    chunks = []
    downloaded = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        downloaded += len(chunk)
        if downloaded > PDF_MAX_DOWNLOAD_BYTES:
            raise PdfVerificationSkipped(
                f"La descarga superó el límite de "
                f"{PDF_MAX_DOWNLOAD_BYTES} bytes."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _take_local_file(
    local_files: dict[str, list[Path]],
    file_name: str,
) -> Path | None:
    matches = local_files.get(_local_match_name(file_name), [])
    return matches.pop(0) if matches else None


def _build_pdf_families(
    appearances: list[dict[str, Any]],
    existing_analysis: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    name_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in appearances:
        canonical_name = item.get("canonical_name")
        if canonical_name:
            name_buckets[canonical_name].append(item)

    groups = []
    for value, items in name_buckets.items():
        if len(items) < 2:
            continue
        groups.append(_family_payload(items, value))

    existing_ids = {
        group.get("evidence", {}).get("value"): group.get("group_id")
        for group in (existing_analysis or {}).get("proposed_groups", [])
        if group.get("group_id")
    }
    used_numbers = [
        int(match.group(1))
        for group_id in existing_ids.values()
        if (match := re.fullmatch(r"pdf_family_(\d+)", group_id or ""))
    ]
    next_number = max(used_numbers, default=0) + 1
    for group in groups:
        canonical_name = group.get("evidence", {}).get("value")
        group_id = existing_ids.get(canonical_name)
        if not group_id:
            group_id = f"pdf_family_{next_number:03d}"
            next_number += 1
        group["group_id"] = group_id
        group["verification"] = _existing_verification(
            existing_analysis or {},
            group_id,
            group.get("appearance_ids", []),
        ) or group["verification"]
    return groups


def _existing_verification(
    existing_analysis: dict[str, Any],
    group_id: str,
    appearance_ids: list[str],
) -> dict[str, Any] | None:
    for group in existing_analysis.get("proposed_groups", []):
        if group.get("group_id") != group_id:
            continue
        if set(group.get("appearance_ids", [])) == set(appearance_ids):
            return group.get("verification")
        return None
    return None


def _family_payload(
    items: list[dict[str, Any]],
    canonical_name: str,
) -> dict[str, Any]:
    appearance_ids = [item["appearance_id"] for item in items]
    uses = sorted({item.get("existing_use") for item in items if item.get("existing_use")})
    urls = list(dict.fromkeys(item.get("detected_url", "") for item in items))
    suggested_use = uses[0] if len(uses) == 1 else "mixed"

    return {
        "group_id": "",
        "group_kind": "candidate_family",
        "certainty": "unverified",
        "evidence": {
            "field": "canonical_name_from_url",
            "value": canonical_name,
            "appearance_count": len(items),
            "analysis_statuses": ["not_verified"],
        },
        "appearance_ids": appearance_ids,
        "proposed_canonical_resource": {
            "resource_id": f"pdf_{canonical_name}",
            "display_name": items[0].get("label") or canonical_name,
            "resource_type": "pdf",
            "proposed_canonical_url": urls[0] if urls else None,
            "selected_canonical_url": None,
            "alternative_urls": urls[1:],
            "suggested_default_use": suggested_use,
            "review_status": "pending_human_confirmation",
        },
        "verification": {
            "status": "not_started",
            "verified_at": None,
            "all_appearances_same": None,
            "partitions": [],
            "unverified_appearance_ids": appearance_ids,
        },
    }


def _build_verification(
    family_id: str,
    appearances: list[dict[str, Any]],
) -> dict[str, Any]:
    analyzed = [
        item for item in appearances
        if item.get("analysis", {}).get("status") == "analyzed"
    ]
    unverified = [
        item.get("appearance_id")
        for item in appearances
        if item.get("analysis", {}).get("status") != "analyzed"
    ]
    content_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in analyzed:
        analysis = item.get("analysis", {})
        key = (
            analysis.get("normalized_text_sha256")
            or f"binary:{analysis.get('binary_sha256')}"
        )
        content_buckets[key].append(item)

    partitions = []
    for index, items in enumerate(content_buckets.values(), start=1):
        binary_hashes = {
            item.get("analysis", {}).get("binary_sha256")
            for item in items
        }
        certainty = (
            "exact_binary_duplicate"
            if len(items) > 1 and len(binary_hashes) == 1
            else "probable_same_content"
            if len(items) > 1
            else "distinct_content"
        )
        partition_id = f"{family_id}_part_{index:03d}"
        partitions.append(
            {
                "partition_id": partition_id,
                "certainty": certainty,
                "appearance_ids": [
                    item.get("appearance_id") for item in items
                ],
                "binary_sha256_values": sorted(binary_hashes),
                "normalized_text_sha256": (
                    items[0].get("analysis", {}).get(
                        "normalized_text_sha256"
                    )
                    or None
                ),
                "derived_relations": _derived_relations(
                    partition_id,
                    items,
                ),
            }
        )

    complete = bool(appearances) and not unverified
    return {
        "status": "complete" if complete else "partial",
        "verified_at": now_iso(),
        "all_appearances_same": complete and len(partitions) == 1,
        "partitions": partitions,
        "unverified_appearance_ids": unverified,
    }


def _derived_relations(
    target_id: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    relations_by_node: dict[str, list[str]] = defaultdict(list)
    for item in items:
        relations_by_node[item.get("source_node_id", "")].append(
            item["appearance_id"]
        )
    return [
        {
            "source_node_id": source_node_id,
            "target_resource_id": target_id,
            "relation": "uses_resource",
            "derived_from": derived_from,
            "use_override": None,
        }
        for source_node_id, derived_from in sorted(relations_by_node.items())
    ]


def _find_family(
    payload: dict[str, Any],
    family_id: str,
) -> dict[str, Any]:
    for family in payload.get("proposed_groups", []):
        if family.get("group_id") == family_id:
            return family
    raise ValueError(f"No existe la familia {family_id} en pdf_analysis.json")


def _analysis_summary(
    appearances: list[dict[str, Any]],
    proposed_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = [
        item.get("analysis", {}).get("status")
        for item in appearances
    ]
    return {
        "appearance_count": len(appearances),
        "analyzed_count": statuses.count("analyzed"),
        "error_count": sum(
            status in {"error", "download_error", "analysis_error"}
            for status in statuses
        ),
        "download_error_count": statuses.count("download_error"),
        "analysis_error_count": statuses.count("analysis_error"),
        "skipped_by_policy_count": statuses.count("skipped_by_policy"),
        "not_attempted_count": statuses.count("not_attempted_local_only"),
        "proposed_group_count": len(proposed_groups),
        "verified_family_count": sum(
            group.get("verification", {}).get("status") in {"complete", "partial"}
            for group in proposed_groups
        ),
        "partition_count": sum(
            len(group.get("verification", {}).get("partitions", []))
            for group in proposed_groups
        ),
    }


def _file_name(url: str) -> str:
    return unquote(urlparse(url).path).rsplit("/", 1)[-1]


def _local_match_name(file_name: str) -> str:
    lowered = file_name.lower()
    return re.sub(r"\s+\(\d+\)(?=\.pdf$)", "", lowered)


def _canonical_pdf_name(file_name: str) -> str:
    base = _local_match_name(file_name).removesuffix(".pdf")
    base = re.sub(r"(codigosdepatologiasab24)\d+$", r"\1", base)
    base = re.sub(r"[_-]\d+$", "", base)
    base = re.sub(r"\d{6,}$", "", base)
    base = re.sub(r"[^a-z0-9]+", "_", base)
    return base.strip("_")

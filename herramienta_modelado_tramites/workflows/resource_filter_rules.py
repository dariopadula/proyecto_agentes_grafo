from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso


DEFAULT_RESOURCE_FILTER_RULES = [
    {
        "rule_id": "rule_001",
        "match_type": "url_contains",
        "pattern": "/print/pdf/node/",
        "action": "discard",
        "reason": "Version PDF imprimible generada desde la pagina HTML.",
        "enabled": True,
    },
    {
        "rule_id": "rule_002",
        "match_type": "url_contains",
        "pattern": "wa.me/message/",
        "action": "discard",
        "reason": "Canal de reporte o feedback, no es recurso del tramite.",
        "enabled": True,
    },
    {
        "rule_id": "rule_003",
        "match_type": "url_contains",
        "pattern": "/formularios/comunicar-un-error",
        "action": "discard",
        "reason": "Formulario administrativo para reportar errores de la pagina.",
        "enabled": True,
    },
]


def load_or_create_resource_filter_rules(project_id: str) -> dict[str, Any]:
    """Carga reglas de filtrado del proyecto o crea las reglas iniciales."""
    rules_path = PROJECTS_DIR / project_id / "resource_filter_rules.json"
    if rules_path.exists():
        return load_json(rules_path)

    payload = {
        "project_id": project_id,
        "updated_at": now_iso(),
        "rules": DEFAULT_RESOURCE_FILTER_RULES,
    }
    save_json(payload, rules_path)
    return payload


def apply_resource_filter_rules(
    resources: list[dict[str, Any]],
    rules_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separa recursos aceptados y descartados segun reglas configurables."""
    kept_resources = []
    discarded_resources = []
    rules = [
        rule
        for rule in rules_payload.get("rules", [])
        if rule.get("enabled", True) and rule.get("action") == "discard"
    ]

    for resource in resources:
        matching_rule = _matching_rule(resource, rules)
        if matching_rule:
            discarded = dict(resource)
            discarded["status"] = "discarded_by_rule"
            discarded["discard_rule_id"] = matching_rule.get("rule_id", "")
            discarded["discard_reason"] = matching_rule.get("reason", "")
            discarded_resources.append(discarded)
            continue
        kept_resources.append(resource)

    return kept_resources, discarded_resources


def save_resource_filter_configuration(
    project_id: str,
    enabled_rule_ids: list[str],
    match_type: str,
    pattern: str,
    reason: str,
) -> dict[str, Any]:
    """Actualiza reglas del proyecto antes de regenerar agrupamientos."""
    if match_type and match_type not in {"url_contains", "text_contains"}:
        raise ValueError("Tipo de coincidencia inválido")
    payload = load_or_create_resource_filter_rules(project_id)
    enabled = set(enabled_rule_ids)
    for rule in payload.get("rules", []):
        rule["enabled"] = rule.get("rule_id") in enabled

    clean_pattern = pattern.strip()
    if clean_pattern:
        next_number = max(
            [
                int(str(rule.get("rule_id", "rule_000")).rsplit("_", 1)[-1])
                for rule in payload.get("rules", [])
                if str(rule.get("rule_id", "")).rsplit("_", 1)[-1].isdigit()
            ],
            default=0,
        ) + 1
        payload.setdefault("rules", []).append(
            {
                "rule_id": f"rule_{next_number:03d}",
                "match_type": match_type or "url_contains",
                "pattern": clean_pattern,
                "action": "discard",
                "reason": reason.strip() or "Exclusión definida para el proyecto.",
                "enabled": True,
            }
        )
    payload["updated_at"] = now_iso()
    save_json(payload, PROJECTS_DIR / project_id / "resource_filter_rules.json")
    return payload


def _matching_rule(
    resource: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for rule in rules:
        if _matches(resource, rule):
            return rule
    return None


def _matches(resource: dict[str, Any], rule: dict[str, Any]) -> bool:
    match_type = rule.get("match_type")
    pattern = str(rule.get("pattern", "")).lower()
    if not pattern:
        return False

    if match_type == "url_contains":
        return pattern in str(resource.get("url", "")).lower()
    if match_type == "text_contains":
        text = " ".join(
            [
                str(resource.get("title", "")),
                str(resource.get("anchor_text", "")),
                str(resource.get("source_context", "")),
            ]
        ).lower()
        return pattern in text
    return False

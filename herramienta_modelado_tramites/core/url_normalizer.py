from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit


DOCUMENT_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".ods",
    ".odt",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".xls",
    ".xlsx",
    ".zip",
}

AGENDA_NON_IDENTITY_PARAMETERS = {
    "pagina_retorno",
    "solo_cuerpo",
}

AGENDA_IDENTITY_PARAMETERS = {
    "agenda",
    "recurso",
}


def analyze_url(url: str, resource_type: str = "") -> dict[str, Any]:
    """Devuelve componentes normalizados sin afirmar identidad real."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    path = _normalize_path(parsed.path)
    query_pairs = _normalized_query_pairs(parsed.query)
    normalized_query = urlencode(query_pairs, doseq=True)
    normalized_url = urlunsplit(
        (scheme, host, path, normalized_query, "")
    )
    parameters = _parameters_payload(query_pairs)
    kind = _functional_kind(
        resource_type=resource_type,
        host=host,
        path=path,
    )
    is_document = _is_document_path(path)

    if kind == "agenda":
        identity_pairs = [
            (key, value)
            for key, value in query_pairs
            if key in AGENDA_IDENTITY_PARAMETERS
        ]
        ignored_pairs = [
            (key, value)
            for key, value in query_pairs
            if key not in AGENDA_IDENTITY_PARAMETERS
        ]
    else:
        identity_pairs = query_pairs
        ignored_pairs = []

    identity_query = urlencode(identity_pairs, doseq=True)
    identity_key = urlunsplit(("", host, path, identity_query, ""))

    return {
        "normalized_url": normalized_url,
        "identity_key": identity_key,
        "scheme": scheme,
        "host": host,
        "path": path,
        "parameters": parameters,
        "identity_parameters": _parameters_payload(identity_pairs),
        "non_identity_parameters": _parameters_payload(ignored_pairs),
        "unexpected_parameters": _parameters_payload(
            [
                (key, value)
                for key, value in query_pairs
                if kind == "agenda"
                and key not in AGENDA_IDENTITY_PARAMETERS
                and key not in AGENDA_NON_IDENTITY_PARAMETERS
            ]
        ),
        "functional_kind": kind,
        "is_document": is_document,
        "document_extension": (
            PurePosixPath(path).suffix.lower() if is_document else None
        ),
    }


def _normalize_path(path: str) -> str:
    decoded = unquote(path or "/")
    segments = [segment for segment in decoded.split("/") if segment]
    normalized = "/" + "/".join(segments)
    if path.endswith("/") and normalized != "/":
        normalized += "/"
    return quote(normalized, safe="/:@-._~")


def _normalized_query_pairs(query: str) -> list[tuple[str, str]]:
    pairs = [
        (unquote(key).strip().lower(), unquote(value).strip())
        for key, value in parse_qsl(query, keep_blank_values=True)
    ]
    return sorted(pairs, key=lambda item: (item[0], item[1]))


def _parameters_payload(
    pairs: list[tuple[str, str]],
) -> dict[str, str | list[str]]:
    values_by_key: dict[str, list[str]] = {}
    for key, value in pairs:
        values_by_key.setdefault(key, []).append(value)
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in values_by_key.items()
    }


def _functional_kind(resource_type: str, host: str, path: str) -> str:
    current = resource_type.lower().strip()
    path_lower = unquote(path).lower()
    host_lower = host.lower()

    if current == "agenda" or "agendarreserva" in path_lower:
        return "agenda"
    if "digesto" in host_lower or "digesto" in path_lower:
        return "digesto"
    if "normativa" in host_lower or current == "normativa":
        return "normativa"
    if current == "articulo" or "/articulo/" in path_lower:
        return "articulo"
    if current == "formulario":
        return "formulario_web"
    if current == "tramite_relacionado":
        return "tramite_relacionado"
    if current == "link":
        return "enlace_general"
    return current or "desconocido"


def _is_document_path(path: str) -> bool:
    return PurePosixPath(unquote(path)).suffix.lower() in DOCUMENT_EXTENSIONS

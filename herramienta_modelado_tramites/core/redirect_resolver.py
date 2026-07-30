from typing import Any
from urllib.parse import urljoin
from urllib.parse import urlsplit

import requests


REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


def resolve_redirect_chain(
    url: str,
    allowed_hosts: set[str],
    max_redirects: int = 5,
    timeout_seconds: int = 10,
    request_get=None,
) -> dict[str, Any]:
    """Sigue solo redirecciones HTTP, con dominio, ciclo y longitud acotados."""
    request_get = request_get or requests.get
    current_url = url
    chain = [url]
    visited = {url}

    for _ in range(max_redirects + 1):
        if not _is_allowed(current_url, allowed_hosts):
            return _result(
                "blocked_domain", url, current_url, chain,
                "El destino sale de los dominios permitidos.",
            )
        try:
            response = request_get(
                current_url,
                allow_redirects=False,
                timeout=(5, timeout_seconds),
                headers={
                    "User-Agent": (
                        "herramienta-modelado-tramites/0.1 "
                        "(POC de revision asistida)"
                    )
                },
                stream=True,
            )
        except requests.RequestException as error:
            return _result(
                "request_error", url, current_url, chain,
                f"{type(error).__name__}: {error}",
            )

        try:
            if response.status_code not in REDIRECT_STATUS_CODES:
                status = "resolved" if len(chain) > 1 else "no_redirect"
                return _result(status, url, current_url, chain)
            location = response.headers.get("Location")
            if not location:
                return _result(
                    "invalid_redirect", url, current_url, chain,
                    "La redirección no contiene Location.",
                )
            next_url = urljoin(current_url, location)
        finally:
            response.close()

        if next_url in visited:
            return _result(
                "cycle_detected", url, current_url, chain + [next_url],
                "La cadena de redirecciones contiene un ciclo.",
            )
        if len(chain) > max_redirects:
            return _result(
                "max_redirects_exceeded", url, current_url, chain,
                f"Se superó el máximo de {max_redirects} redirecciones.",
            )
        visited.add(next_url)
        chain.append(next_url)
        current_url = next_url

    return _result(
        "max_redirects_exceeded", url, current_url, chain,
        f"Se superó el máximo de {max_redirects} redirecciones.",
    )


def _is_allowed(url: str, allowed_hosts: set[str]) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme.lower() in {"http", "https"}
        and (parsed.hostname or "").lower() in allowed_hosts
    )


def _result(
    status: str,
    original_url: str,
    final_url: str,
    chain: list[str],
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "original_url": original_url,
        "final_url": final_url,
        "redirect_count": max(0, len(chain) - 1),
        "chain": chain,
        "error": error,
    }

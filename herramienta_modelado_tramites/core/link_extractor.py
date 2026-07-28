from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup


ALLOWED_DOMAINS = {
    "montevideo.gub.uy",
    "tramites.montevideo.gub.uy",
    "www.montevideo.gub.uy",
    "normativa.montevideo.gub.uy",
}

TRAMITE_RESULT_PATH_PARTS = {
    "/tramites-y-tributos/solicitud/",
    "/tramites-y-tributos/renovacion/",
    "/tramites-y-tributos/certificado/",
    "/tramites-y-tributos/registro/",
    "/tramites-y-tributos/exoneracion/",
}


def extract_candidate_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Extrae links candidatos para revision humana."""
    soup = BeautifulSoup(html, "html.parser")
    result_tags = soup.select(".listado-tramites.views-row .views-field-title a")

    if result_tags:
        return _extract_from_tags(
            tags=result_tags,
            base_url=base_url,
            source_context="Listado de resultados del buscador",
            detection_reason="Link encontrado en listado principal de tramites",
            only_tramite_paths=True,
        )

    return _extract_from_tags(
        tags=soup.find_all("a", href=True),
        base_url=base_url,
        source_context="Links internos de la pagina inicial",
        detection_reason="Link interno encontrado en la pagina inicial",
        only_tramite_paths=False,
    )


def _extract_from_tags(
    tags: list,
    base_url: str,
    source_context: str,
    detection_reason: str,
    only_tramite_paths: bool,
) -> list[dict[str, str]]:
    links = []
    seen_urls = set()

    for tag in tags:
        url = _normalize_url(base_url, tag.get("href", ""))
        if not url or url in seen_urls:
            continue
        if not _is_allowed_url(url):
            continue
        if only_tramite_paths and not _looks_like_tramite_result(url):
            continue

        seen_urls.add(url)
        links.append(
            {
                "url": url,
                "title": _clean_text(tag.get_text(" ", strip=True)) or url,
                "anchor_text": _clean_text(tag.get_text(" ", strip=True)),
                "source_context": source_context,
                "detection_reason": detection_reason,
                "detected_role": "candidate",
                "status": "pending_review",
            }
        )

    return [
        {
            "link_id": f"link_{index:03d}",
            **link,
        }
        for index, link in enumerate(links, start=1)
    ]


def _normalize_url(base_url: str, href: str) -> str:
    if not href:
        return ""
    absolute = urljoin(base_url, href)
    return urldefrag(absolute).url


def _is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc in ALLOWED_DOMAINS


def _looks_like_tramite_result(url: str) -> bool:
    path = urlparse(url).path
    return any(part in path for part in TRAMITE_RESULT_PATH_PARTS)


def _clean_text(value: str) -> str:
    return " ".join(value.split())

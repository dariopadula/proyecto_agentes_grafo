from typing import Any
from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup


ALLOWED_RESOURCE_DOMAINS = {
    "montevideo.gub.uy",
    "tramites.montevideo.gub.uy",
    "www.montevideo.gub.uy",
    "normativa.montevideo.gub.uy",
}


def extract_internal_resources(html: str, base_url: str) -> dict[str, Any]:
    """Extrae links internos relevantes encontrados dentro de una pagina aceptada."""
    soup = BeautifulSoup(html, "html.parser")
    container = _main_container(soup)
    resources = []
    seen_urls = set()

    for tag in container.find_all("a", href=True):
        url = _normalize_url(base_url, tag.get("href", ""))
        if not url or url in seen_urls:
            continue
        if not _is_allowed_resource(url):
            continue
        if url == base_url:
            continue

        seen_urls.add(url)
        anchor_text = _clean_text(tag.get_text(" ", strip=True))
        resources.append(
            {
                "resource_id": f"resource_{len(resources) + 1:03d}",
                "url": url,
                "title": anchor_text or url,
                "anchor_text": anchor_text,
                "resource_type": _resource_type(url, anchor_text),
                "source_context": _nearby_text(tag),
                "status": "pending_review",
            }
        )

    return {
        "page_title": _page_title(soup),
        "resources": resources,
    }


def _main_container(soup: BeautifulSoup):
    for selector in ["main", "article", ".region-content", "#main-content", "body"]:
        container = soup.select_one(selector)
        if container:
            return container
    return soup


def _normalize_url(base_url: str, href: str) -> str:
    if not href:
        return ""
    absolute = urljoin(base_url, href)
    return urldefrag(absolute).url


def _is_allowed_resource(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc in ALLOWED_RESOURCE_DOMAINS


def _resource_type(url: str, anchor_text: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.lower()
    text = anchor_text.lower()

    if path.endswith(".pdf") or ".pdf" in path:
        return "pdf"
    if "agenda" in path or "agenda" in text:
        return "agenda"
    if "formulario" in path or "formulario" in text:
        return "formulario"
    if "normativa" in parsed.netloc or "normativa" in path or "decreto" in text:
        return "normativa"
    if "articulo" in path or "articulo" in text or "artículo" in text:
        return "articulo"
    if "/tramites-y-tributos/" in path:
        return "tramite_relacionado"
    return "link"


def _nearby_text(tag) -> str:
    parent = tag.find_parent(["li", "p", "div", "section", "article"])
    if not parent:
        return ""
    return _clean_text(parent.get_text(" ", strip=True))[:500]


def _page_title(soup: BeautifulSoup) -> str:
    heading = soup.find(["h1", "h2"])
    if heading:
        return _clean_text(heading.get_text(" ", strip=True))
    if soup.title:
        return _clean_text(soup.title.get_text(" ", strip=True))
    return ""


def _clean_text(value: str) -> str:
    return " ".join(value.split())

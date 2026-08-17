from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.parse import parse_qs

from bs4 import BeautifulSoup


ALLOWED_DOMAINS = {
    "montevideo.gub.uy",
    "tramites.montevideo.gub.uy",
    "www.montevideo.gub.uy",
    "normativa.montevideo.gub.uy",
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
        )

    return _extract_from_tags(
        tags=soup.find_all("a", href=True),
        base_url=base_url,
        source_context="Links internos de la pagina inicial",
        detection_reason="Link interno encontrado en la pagina inicial",
    )


def extract_pagination_urls(
    html: str,
    current_url: str,
    start_url: str,
) -> list[str]:
    """Extrae paginas numeradas del mismo buscador, sin seguir navegacion ajena."""
    soup = BeautifulSoup(html, "html.parser")
    start = urlparse(start_url)
    urls_by_page: dict[int, str] = {}
    for tag in soup.find_all("a", href=True):
        url = _normalize_url(current_url, tag.get("href", ""))
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc != start.netloc
            or parsed.path != start.path
        ):
            continue
        page_values = parse_qs(parsed.query).get("page", [])
        if len(page_values) != 1 or not page_values[0].isdigit():
            continue
        page_number = int(page_values[0])
        if page_number == 0:
            # Drupal expone a veces ?page=0 como alias de la URL inicial.
            continue
        urls_by_page.setdefault(page_number, url)
    return [urls_by_page[number] for number in sorted(urls_by_page)]


def _extract_from_tags(
    tags: list,
    base_url: str,
    source_context: str,
    detection_reason: str,
) -> list[dict[str, str]]:
    links = []
    seen_urls = set()

    for tag in tags:
        url = _normalize_url(base_url, tag.get("href", ""))
        if not url or url in seen_urls:
            continue
        if not _is_allowed_url(url):
            continue
        seen_urls.add(url)
        links.append(
            {
                "url": url,
                "title": _clean_text(tag.get_text(" ", strip=True)) or url,
                "anchor_text": _clean_text(tag.get_text(" ", strip=True)),
                "source_context": source_context,
                "detection_reason": detection_reason,
                "url_category": _url_category(url),
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


def _url_category(url: str) -> str:
    """Conserva la categoria aparente de la URL sin usarla como filtro."""
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "tramites-y-tributos":
        return parts[1]
    return ""


def _clean_text(value: str) -> str:
    return " ".join(value.split())

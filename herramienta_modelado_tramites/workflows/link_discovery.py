from typing import Any
from collections import deque

from config import DISCOVERY_MAX_PAGES
from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.link_extractor import extract_candidate_links
from core.link_extractor import extract_pagination_urls
from core.time_utils import now_iso
from core.web_reader import fetch_page


def discover_candidate_links(project_id: str, actor: str) -> dict[str, Any]:
    """Descarga la URL inicial del proyecto y guarda links candidatos."""
    project_dir = PROJECTS_DIR / project_id
    project_path = project_dir / "project.json"
    candidate_links_path = project_dir / "candidate_links.json"
    change_log_path = project_dir / "change_log.json"

    project = load_json(project_path)
    previous_project = dict(project)
    discovery = _discover_pages(project["start_url"])
    links = discovery["links"]
    timestamp = now_iso()

    candidate_links = {
        "project_id": project_id,
        "source_url": project["start_url"],
        "generated_at": timestamp,
        "pages_scanned": discovery["pages_scanned"],
        "page_urls": discovery["page_urls"],
        "page_errors": discovery["page_errors"],
        "page_limit_reached": discovery["page_limit_reached"],
        "links": links,
    }
    save_json(candidate_links, candidate_links_path)

    project["status"] = "link_review"
    project["updated_at"] = timestamp
    save_json(project, project_path)

    change_log = load_json(change_log_path)
    change_log["events"].append(
        {
            "event_id": f"event_{len(change_log['events']) + 1:03d}",
            "timestamp": timestamp,
            "actor": actor,
            "action": "detect_candidate_links",
            "target_type": "project",
            "target_id": project_id,
            "summary": (
                f"Se detectaron {len(links)} links candidatos en "
                f"{discovery['pages_scanned']} paginas."
            ),
            "before": {
                "status": previous_project.get("status"),
                "links_count": None,
            },
            "after": {
                "status": project["status"],
                "links_count": len(links),
                "pages_scanned": discovery["pages_scanned"],
                "page_error_count": len(discovery["page_errors"]),
            },
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "links_count": len(links),
        "pages_scanned": discovery["pages_scanned"],
        "page_errors": discovery["page_errors"],
        "page_limit_reached": discovery["page_limit_reached"],
        "candidate_links_path": str(candidate_links_path),
    }


def _discover_pages(start_url: str) -> dict[str, Any]:
    queue = deque([start_url])
    queued = {start_url}
    visited: set[str] = set()
    page_urls: list[str] = []
    page_errors: list[dict[str, str]] = []
    links_by_url: dict[str, dict[str, Any]] = {}

    while queue and len(visited) < DISCOVERY_MAX_PAGES:
        page_url = queue.popleft()
        if page_url in visited:
            continue
        visited.add(page_url)
        try:
            html = fetch_page(page_url)
        except Exception as error:
            if page_url == start_url:
                raise
            page_errors.append({"url": page_url, "error": str(error)})
            continue

        page_urls.append(page_url)
        for link in extract_candidate_links(html, page_url):
            link_url = link.get("url", "")
            if not link_url:
                continue
            existing = links_by_url.get(link_url)
            if existing:
                if page_url not in existing["source_page_urls"]:
                    existing["source_page_urls"].append(page_url)
                continue
            item = {key: value for key, value in link.items() if key != "link_id"}
            item["source_page_urls"] = [page_url]
            links_by_url[link_url] = item

        for pagination_url in extract_pagination_urls(html, page_url, start_url):
            if pagination_url not in queued and pagination_url not in visited:
                queue.append(pagination_url)
                queued.add(pagination_url)

    links = [
        {"link_id": f"link_{index:03d}", **link}
        for index, link in enumerate(links_by_url.values(), start=1)
    ]
    return {
        "links": links,
        "pages_scanned": len(page_urls),
        "page_urls": page_urls,
        "page_errors": page_errors,
        "page_limit_reached": bool(queue),
    }

from typing import Any

from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.link_extractor import extract_candidate_links
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
    html = fetch_page(project["start_url"])
    links = extract_candidate_links(html, project["start_url"])
    timestamp = now_iso()

    candidate_links = {
        "project_id": project_id,
        "source_url": project["start_url"],
        "generated_at": timestamp,
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
            "summary": f"Se detectaron {len(links)} links candidatos.",
            "before": {
                "status": previous_project.get("status"),
                "links_count": None,
            },
            "after": {
                "status": project["status"],
                "links_count": len(links),
            },
        }
    )
    save_json(change_log, change_log_path)

    return {
        "project_id": project_id,
        "links_count": len(links),
        "candidate_links_path": str(candidate_links_path),
    }

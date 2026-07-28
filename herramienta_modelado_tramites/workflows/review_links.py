from typing import Any

from config import OUTPUTS_DIR
from config import PROJECTS_DIR
from core.json_store import load_json
from ui.review_links_page import save_review_links_html


def build_review_links(project_id: str) -> dict[str, Any]:
    """Genera la vista HTML de revision de links candidatos."""
    project_dir = PROJECTS_DIR / project_id
    output_dir = OUTPUTS_DIR / project_id

    project = load_json(project_dir / "project.json")
    candidate_links = load_json(project_dir / "candidate_links.json")
    human_review = load_json(project_dir / "human_review.json")

    output_path = output_dir / "review_links.html"
    save_review_links_html(
        project=project,
        candidate_links=candidate_links,
        human_review=human_review,
        output_path=output_path,
    )

    return {
        "project_id": project_id,
        "links_count": len(candidate_links.get("links", [])),
        "output_path": str(output_path),
    }

from pathlib import Path
import shutil
from typing import Any

from config import DATA_DIR
from config import OUTPUTS_DIR
from config import PROJECTS_DIR
from core.json_store import load_json
from core.json_store import save_json
from core.time_utils import now_iso


DELETED_PROJECTS_DIR = DATA_DIR / "deleted_projects"


def delete_project_recoverably(
    project_id: str,
    confirmation: str,
    actor: str,
) -> dict[str, Any]:
    """Retira un proyecto activo y conserva una copia recuperable completa."""
    project_dir = PROJECTS_DIR / project_id
    project_path = project_dir / "project.json"
    if not project_path.exists():
        raise ValueError("El proyecto no existe o ya fue eliminado.")
    if confirmation.strip() != project_id:
        raise ValueError("La confirmacion no coincide con el identificador del proyecto.")

    project = load_json(project_path)
    timestamp = now_iso()
    archive_id = f"{project_id}__{timestamp.replace(':', '-')}"
    archive_dir = DELETED_PROJECTS_DIR / archive_id
    archive_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "archive_id": archive_id,
        "project_id": project_id,
        "project_name": project.get("name"),
        "deleted_at": timestamp,
        "deleted_by": actor,
        "recoverable": True,
    }
    save_json(metadata, archive_dir / "deletion.json")
    shutil.move(str(project_dir), str(archive_dir / "project"))

    output_dir = OUTPUTS_DIR / project_id
    if output_dir.exists():
        shutil.move(str(output_dir), str(archive_dir / "outputs"))

    return {
        "project_id": project_id,
        "archive_dir": str(archive_dir),
        "recoverable": True,
    }

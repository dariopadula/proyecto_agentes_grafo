from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
OUTPUTS_DIR = BASE_DIR / "outputs"

DEFAULT_ACTOR = "funcionario"

LINK_ROLES = {
    "terminal_case",
    "auxiliary_info",
    "related_procedure",
    "shared_resource",
    "discarded",
    "needs_review",
}

LINK_ROLE_LABELS = {
    "terminal_case": "Caso terminal",
    "auxiliary_info": "Informacion auxiliar",
    "related_procedure": "Tramite relacionado",
    "shared_resource": "Recurso compartido",
    "discarded": "Descartar",
    "needs_review": "Requiere revision",
}

PROJECT_STATUSES = {
    "draft",
    "link_review",
    "reviewed",
    "closed",
}

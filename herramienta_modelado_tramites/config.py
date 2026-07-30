from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
OUTPUTS_DIR = BASE_DIR / "outputs"

DEFAULT_ACTOR = "funcionario"

PDF_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
PDF_MAX_TEXT_PAGES = 100
PDF_MAX_TEXT_CHARACTERS = 1_000_000
PDF_DOWNLOAD_TIMEOUT_SECONDS = 20

AUXILIARY_LINK_MAX_REDIRECTS = 5
AUXILIARY_LINK_REDIRECT_TIMEOUT_SECONDS = 10

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

import requests


def fetch_page(url: str) -> str:
    """Descarga una pagina HTML con un User-Agent identificable."""
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": (
                "herramienta-modelado-tramites/0.1 "
                "(POC de revision asistida)"
            )
        },
    )
    response.raise_for_status()
    return response.text

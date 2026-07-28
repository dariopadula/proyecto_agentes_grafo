from html import escape


def html_escape(value: object) -> str:
    """Escapa texto para insertarlo en HTML."""
    return escape(str(value or ""), quote=True)

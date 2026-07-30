import hashlib
import io
import re
from typing import Any

from pypdf import PdfReader


def analyze_pdf_content(
    content: bytes,
    max_text_pages: int | None = None,
    max_text_characters: int | None = None,
) -> dict[str, Any]:
    """Calcula evidencia deterministica sin interpretar semanticamente el PDF."""
    reader = PdfReader(io.BytesIO(content))
    page_limit = min(len(reader.pages), max_text_pages or len(reader.pages))
    text_parts = []
    extraction_truncated = page_limit < len(reader.pages)
    extracted_characters = 0
    for page in reader.pages[:page_limit]:
        text = page.extract_text() or ""
        text_parts.append(text)
        extracted_characters += len(text)
        if (
            max_text_characters is not None
            and extracted_characters >= max_text_characters
        ):
            extraction_truncated = True
            break
    extracted_text = " ".join(text_parts)
    if max_text_characters is not None:
        extracted_text = extracted_text[:max_text_characters]
    normalized_text = normalize_pdf_text(extracted_text)
    words = re.findall(r"\b\w+\b", normalized_text, flags=re.UNICODE)

    return {
        "size_bytes": len(content),
        "page_count": len(reader.pages),
        "character_count": len(normalized_text),
        "word_count": len(words),
        "binary_sha256": hashlib.sha256(content).hexdigest(),
        "normalized_text_sha256": (
            hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
            if normalized_text
            else ""
        ),
        "encrypted": reader.is_encrypted,
        "text_extraction_truncated": extraction_truncated,
    }


def normalize_pdf_text(text: str) -> str:
    """Normaliza espacios y mayusculas para comparar texto extraido."""
    return re.sub(r"\s+", " ", text).strip().lower()

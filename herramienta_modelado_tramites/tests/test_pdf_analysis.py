import io
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from pypdf import PdfWriter

from core.pdf_analyzer import analyze_pdf_content
from workflows.pdf_analysis import (
    _build_pdf_families,
    _build_verification,
    _canonical_pdf_name,
    _download_pdf,
    _local_match_name,
    _pdf_candidates,
)


class PdfAnalyzerTests(unittest.TestCase):
    def test_download_uses_browser_compatible_headers_and_origin_referer(self):
        response = Mock()
        response.headers = {"Content-Length": "3"}
        response.iter_content.return_value = [b"pdf"]
        response.raise_for_status.return_value = None
        with patch("workflows.pdf_analysis.requests.get", return_value=response) as get:
            content = _download_pdf("https://example.test/files/doc.pdf")

        self.assertEqual(content, b"pdf")
        headers = get.call_args.kwargs["headers"]
        self.assertTrue(headers["User-Agent"].startswith("Mozilla/5.0"))
        self.assertEqual(headers["Referer"], "https://example.test/")

    def test_pending_pdfs_are_candidates_before_individual_review(self):
        node_resources = {
            "pages": [
                {
                    "link_id": "node_1",
                    "title": "Trámite",
                    "resources": [
                        {
                            "resource_id": "resource_001",
                            "resource_type": "pdf",
                            "title": "Documento",
                            "url": "https://example.test/documento_0.pdf",
                        }
                    ],
                    "discarded_resources": [],
                }
            ]
        }

        candidates = _pdf_candidates(node_resources, {"decisions": []})

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["appearance_id"],
            "node_1::resource_001",
        )
        self.assertIsNone(candidates[0]["existing_use"])

    def test_blank_pdf_analysis_is_deterministic(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        stream = io.BytesIO()
        writer.write(stream)

        first = analyze_pdf_content(stream.getvalue())
        second = analyze_pdf_content(stream.getvalue())

        self.assertEqual(first["page_count"], 1)
        self.assertEqual(first["binary_sha256"], second["binary_sha256"])
        self.assertEqual(
            first["normalized_text_sha256"],
            second["normalized_text_sha256"],
        )

    def test_text_extraction_respects_page_limit(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=100, height=100)
        stream = io.BytesIO()
        writer.write(stream)

        result = analyze_pdf_content(
            stream.getvalue(),
            max_text_pages=1,
        )

        self.assertEqual(result["page_count"], 2)
        self.assertTrue(result["text_extraction_truncated"])

    def test_browser_duplicate_suffix_does_not_change_canonical_name(self):
        self.assertEqual(
            _canonical_pdf_name("codigosdepatologiasab24 (3).pdf"),
            "codigosdepatologiasab24",
        )
        self.assertEqual(
            _local_match_name("codigosdepatologiasab24 (3).pdf"),
            "codigosdepatologiasab24.pdf",
        )

    def test_initial_families_are_built_only_by_normalized_name(self):
        appearances = [
            _appearance("a1", "node_1", "prices.pdf", "hash-a", "text-a"),
            _appearance("a2", "node_2", "prices_1.pdf", "hash-b", "text-b"),
        ]

        groups = _build_pdf_families(appearances)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["certainty"], "unverified")
        self.assertEqual(groups[0]["verification"]["status"], "not_started")

    def test_verification_partitions_exact_duplicates(self):
        appearances = [
            _appearance("a1", "node_1", "one.pdf", "hash-a", "same-text"),
            _appearance("a2", "node_2", "two.pdf", "hash-a", "same-text"),
        ]

        result = _build_verification("family_1", appearances)

        self.assertTrue(result["all_appearances_same"])
        self.assertEqual(
            result["partitions"][0]["certainty"],
            "exact_binary_duplicate",
        )

    def test_verification_creates_multiple_partitions_and_keeps_unverified(self):
        appearances = [
            _appearance("a1", "node_1", "one.pdf", "hash-a", "text-a"),
            _appearance("a2", "node_2", "two.pdf", "hash-a", "text-a"),
            _appearance("a3", "node_3", "three.pdf", "hash-b", "text-b"),
            _appearance("a4", "node_4", "four.pdf", None, None, "error"),
        ]

        result = _build_verification("family_1", appearances)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["partitions"]), 2)
        self.assertEqual(result["unverified_appearance_ids"], ["a4"])


def _appearance(
    appearance_id,
    node_id,
    filename,
    binary_hash,
    text_hash,
    status="analyzed",
):
    return {
        "appearance_id": appearance_id,
        "source_node_id": node_id,
        "detected_url": f"https://example.test/{filename}",
        "filename": filename,
        "canonical_name": _canonical_pdf_name(filename),
        "existing_use": "process_as_context",
        "analysis": {
            "status": status,
            "binary_sha256": binary_hash,
            "normalized_text_sha256": text_hash,
        },
    }


if __name__ == "__main__":
    unittest.main()

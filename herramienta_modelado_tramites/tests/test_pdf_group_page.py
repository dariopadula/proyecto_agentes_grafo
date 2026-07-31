import unittest

from web_app import _verification_result
from web_app import _friendly_pdf_error


class PdfGroupPageTests(unittest.TestCase):
    def test_network_permission_error_is_presented_in_plain_language(self):
        message = _friendly_pdf_error(
            {"status": "download_error", "error": "PermissionError: WinError 10013"}
        )

        self.assertIn("permiso de red", message)
        self.assertNotIn("ConnectionPool", message)

    def test_consistent_decided_partition_keeps_detail_closed(self):
        family, items = _family_fixture("complete", True)
        decisions = {
            "family_1_part_001": {
                "partition_id": "family_1_part_001",
                "decision_source": "inherited_from_family",
                "identity_decision": "confirmed_same",
            }
        }

        html = _verification_result(
            "demo",
            family,
            items,
            decisions,
            {"verification_reconciliation": "consistent"},
        )

        self.assertIn("<strong>2</strong> verificados", html)
        self.assertIn("<strong>1</strong> documento diferente encontrado", html)
        self.assertIn("<details>", html)
        self.assertNotIn("<details open>", html)

    def test_partial_verification_opens_detail_and_counts_failures(self):
        family, items = _family_fixture("partial", False)
        items[1]["analysis"] = {
            "status": "download_error",
            "error": "Timeout",
        }

        html = _verification_result("demo", family, items, {}, {})

        self.assertIn("<strong>1</strong> no pudieron descargarse", html)
        self.assertIn("<details open>", html)
        self.assertIn("No se pudo descargar este PDF", html)
        self.assertNotIn("Timeout", html)


def _family_fixture(status, all_same):
    items = [
        {
            "appearance_id": "a1",
            "source_node_id": "node_1",
            "source_node_title": "Nodo uno",
            "detected_url": "https://example.test/one.pdf",
            "file_name": "one.pdf",
            "analysis": {"status": "analyzed"},
        },
        {
            "appearance_id": "a2",
            "source_node_id": "node_2",
            "source_node_title": "Nodo dos",
            "detected_url": "https://example.test/two.pdf",
            "file_name": "two.pdf",
            "analysis": {"status": "analyzed"},
        },
    ]
    family = {
        "group_id": "family_1",
        "proposed_canonical_resource": {
            "display_name": "Documento",
            "suggested_default_use": "show_as_link",
        },
        "verification": {
            "status": status,
            "all_appearances_same": all_same,
            "partitions": [
                {
                    "partition_id": "family_1_part_001",
                    "certainty": "exact_binary_duplicate",
                    "appearance_ids": ["a1", "a2"],
                }
            ],
            "unverified_appearance_ids": (
                [] if status == "complete" else ["a2"]
            ),
        },
    }
    return family, items


if __name__ == "__main__":
    unittest.main()

import unittest

from core.url_normalizer import analyze_url
from workflows.auxiliary_link_analysis import _build_appearances
from workflows.auxiliary_link_analysis import _build_groups


class UrlNormalizerTests(unittest.TestCase):
    def test_query_order_and_fragment_do_not_change_identity(self):
        first = analyze_url(
            "https://Example.test/path?b=2&a=1#section",
            "link",
        )
        second = analyze_url(
            "https://example.test/path?a=1&b=2",
            "link",
        )

        self.assertEqual(first["identity_key"], second["identity_key"])
        self.assertNotIn("#", first["normalized_url"])

    def test_agenda_return_page_is_evidence_not_identity(self):
        first = analyze_url(
            "https://www.montevideo.gub.uy/sae/agendarReserva/Paso1.xhtml"
            "?agenda=RENOVCON&recurso=RENCOMUN"
            "&pagina_retorno=https%3A//www.montevideo.gub.uy"
            "&solo_cuerpo=false",
            "agenda",
        )
        second = analyze_url(
            "https://www.montevideo.gub.uy/sae/agendarReserva/Paso1.xhtml"
            "?recurso=RENCOMUN&agenda=RENOVCON"
            "&pagina_retorno=https://www.montevideo.gub.uy",
            "agenda",
        )

        self.assertEqual(first["identity_key"], second["identity_key"])
        self.assertEqual(
            first["identity_parameters"],
            {"agenda": "RENOVCON", "recurso": "RENCOMUN"},
        )
        self.assertIn(
            "pagina_retorno",
            first["non_identity_parameters"],
        )

    def test_different_agenda_resource_is_not_same_identity(self):
        first = analyze_url(
            "https://example.test/agenda?agenda=A&recurso=ONE",
            "agenda",
        )
        second = analyze_url(
            "https://example.test/agenda?agenda=A&recurso=TWO",
            "agenda",
        )

        self.assertNotEqual(first["identity_key"], second["identity_key"])

    def test_unexpected_agenda_parameters_are_only_evidence(self):
        result = analyze_url(
            "https://example.test/agenda"
            "?agenda=A&recurso=ONE&office=central",
            "agenda",
        )

        self.assertNotIn("office", result["identity_parameters"])
        self.assertEqual(
            result["unexpected_parameters"],
            {"office": "central"},
        )

    def test_downloadable_document_is_excluded_by_extension(self):
        result = analyze_url(
            "https://example.test/files/guide.DOCX?download=1",
            "link",
        )

        self.assertTrue(result["is_document"])
        self.assertEqual(result["document_extension"], ".docx")


class AuxiliaryInventoryTests(unittest.TestCase):
    def test_inventory_keeps_discarded_and_excludes_documents(self):
        node_resources = {
            "pages": [
                {
                    "link_id": "link_001",
                    "title": "Node one",
                    "resources": [
                        _resource("resource_001", "https://example.test/a"),
                        _resource(
                            "resource_002",
                            "https://example.test/file.pdf",
                            "pdf",
                        ),
                    ],
                    "discarded_resources": [
                        {
                            **_resource(
                                "resource_003",
                                "https://example.test/report-error",
                                "formulario",
                            ),
                            "discard_rule_id": "rule_1",
                            "discard_reason": "Noise",
                        }
                    ],
                }
            ]
        }
        decisions = {
            "link_001::resource_001": {
                "use": "process_as_context",
                "scope": "node_only",
            }
        }

        appearances, documents = _build_appearances(
            node_resources,
            decisions,
        )

        self.assertEqual(len(appearances), 2)
        self.assertEqual(len(documents), 1)
        self.assertEqual(
            appearances[0]["existing_use"],
            "process_as_context",
        )
        self.assertEqual(
            appearances[1]["filter_status"],
            "discarded_by_rule",
        )

    def test_normalized_group_requires_distinct_original_urls(self):
        appearances = []
        for appearance_id, url in (
            ("a1", "https://example.test/path?b=2&a=1"),
            ("a2", "https://example.test/path?a=1&b=2"),
        ):
            appearances.append(
                {
                    "appearance_id": appearance_id,
                    "source_node_id": appearance_id,
                    "detected_url": url,
                    **analyze_url(url, "link"),
                }
            )

        groups = _build_groups(
            appearances,
            key_field="identity_key",
            prefix="normalized",
            certainty="normalized_equivalent",
            evidence_field="identity_key",
            require_distinct_urls=True,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["evidence"]["appearance_count"], 2)

    def test_group_id_is_preserved_when_an_appearance_is_added(self):
        first = {
            "appearance_id": "a1",
            "source_node_id": "node_1",
            "detected_url": "https://example.test/shared",
        }
        existing = _build_groups(
            [first, {**first, "appearance_id": "a2", "source_node_id": "node_2"}],
            key_field="detected_url",
            prefix="exact_url",
            certainty="exact_url",
            evidence_field="detected_url",
        )
        updated = _build_groups(
            [
                first,
                {**first, "appearance_id": "a2", "source_node_id": "node_2"},
                {**first, "appearance_id": "a3", "source_node_id": "node_3"},
            ],
            key_field="detected_url",
            prefix="exact_url",
            certainty="exact_url",
            evidence_field="detected_url",
            existing_groups=existing,
        )

        self.assertEqual(updated[0]["group_id"], existing[0]["group_id"])
        self.assertEqual(len(updated[0]["appearance_ids"]), 3)


def _resource(resource_id, url, resource_type="link"):
    return {
        "resource_id": resource_id,
        "url": url,
        "title": resource_id,
        "anchor_text": resource_id,
        "resource_type": resource_type,
        "source_context": "",
    }


if __name__ == "__main__":
    unittest.main()

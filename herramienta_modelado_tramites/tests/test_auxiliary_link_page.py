import unittest

from web_app import _auxiliary_group_card
from web_app import _project_id_from_auxiliary_links_path


class AuxiliaryLinkPageTests(unittest.TestCase):
    def test_agenda_card_shows_final_url_and_redirect_evidence(self):
        appearance = {
            "appearance_id": "link_022::resource_005",
            "source_node_id": "link_022",
            "source_node_title": "Renovación profesional",
            "label": "Agenda profesional",
            "detected_url": "https://example.test/intermediate",
            "candidate_canonical_url": (
                "https://www.montevideo.gub.uy/sae/"
                "agendarReserva/Paso1.xhtml"
                "?agenda=RENLICPR&recurso=RENPROF-MEDINT"
            ),
            "identity_parameters": {
                "agenda": "RENLICPR",
                "recurso": "RENPROF-MEDINT",
            },
            "functional_kind": "agenda",
            "existing_use": "show_as_link",
            "filter_status": "reviewable",
            "source_context": "Reservar hora",
            "redirect_resolution": {
                "status": "resolved",
                "redirect_count": 1,
                "error": None,
            },
        }
        group = {
            "group_id": "agenda_001",
            "certainty": "agenda_parameters_match",
            "appearance_ids": ["link_022::resource_005"],
            "source_node_ids": ["link_022"],
            "detected_urls": ["https://example.test/intermediate"],
            "suggested_functional_kind": "agenda",
            "existing_uses": ["show_as_link"],
            "evidence": {
                "value": (
                    "//www.montevideo.gub.uy/sae/agendarReserva/"
                    "Paso1.xhtml?agenda=RENLICPR&recurso=RENPROF-MEDINT"
                ),
                "appearance_count": 1,
            },
        }

        html = _auxiliary_group_card(
            "demo",
            group,
            {appearance["appearance_id"]: appearance},
            "agenda",
            {},
        )

        self.assertIn("Agenda RENLICPR / RENPROF-MEDINT", html)
        self.assertIn("Destino final propuesto", html)
        self.assertIn("Redirección resuelta: 1", html)
        self.assertIn("Coinciden agenda y recurso", html)
        self.assertIn("Guardar y aplicar al grupo", html)

    def test_auxiliary_path_is_recognized(self):
        self.assertEqual(
            _project_id_from_auxiliary_links_path(
                "/projects/demo/auxiliary-links"
            ),
            "demo",
        )
        self.assertIsNone(
            _project_id_from_auxiliary_links_path(
                "/projects/demo/auxiliary-links/extra"
            )
        )


if __name__ == "__main__":
    unittest.main()

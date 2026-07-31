import tempfile
import unittest
from pathlib import Path

from core.json_store import save_json
import web_app


class ResourcePageFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_projects_dir = web_app.PROJECTS_DIR
        web_app.PROJECTS_DIR = Path(self.temp_dir.name)
        project_dir = Path(self.temp_dir.name) / "demo"
        project_dir.mkdir()
        save_json(
            {"project_id": "demo", "name": "Demo"},
            project_dir / "project.json",
        )
        save_json(
            {
                "accepted_links_count": 1,
                "resources_count": 1,
                "discarded_resources_count": 0,
                "pages": [
                    {
                        "link_id": "link_001",
                        "title": "Nodo",
                        "url": "https://example.test/node",
                        "status": "ok",
                        "resources": [
                            {
                                "resource_id": "resource_001",
                                "title": "Agenda",
                                "url": "https://example.test/agenda",
                                "resource_type": "agenda",
                                "anchor_text": "Agenda",
                                "source_context": "Reservar",
                            }
                        ],
                        "discarded_resources": [],
                    }
                ],
            },
            project_dir / "node_resources.json",
        )

    def tearDown(self):
        web_app.PROJECTS_DIR = self.original_projects_dir
        self.temp_dir.cleanup()

    def test_page_restores_filters_and_hides_empty_cards(self):
        html = web_app._resources_page(
            "demo",
            "/projects/demo/resources?discard_filter=kept"
            "&decision_filter=pending&scroll_y=450",
        )

        self.assertIn('initialFilters.get("decision_filter")', html)
        self.assertIn('card.querySelector(".resource-row:not(.hidden)")', html)
        self.assertIn("window.scrollTo(0, restoredScrollY)", html)
        self.assertIn('name="scroll_y"', html)
        self.assertIn("No hay recursos que coincidan", html)

    def test_filter_values_are_sanitized_for_redirect(self):
        filters = web_app._resource_filters_from_form(
            {
                "search_filter": ["agenda profesional"],
                "type_filter": ["agenda"],
                "discard_filter": ["kept"],
                "decision_filter": ["invalid"],
                "scroll_y": ["350"],
            }
        )

        self.assertEqual(filters["discard_filter"], "kept")
        self.assertNotIn("decision_filter", filters)
        self.assertEqual(filters["scroll_y"], "350")
        location = web_app._resource_review_redirect(
            "demo",
            "link_001",
            "resource_001",
            filters,
        )
        self.assertIn("search_filter=agenda+profesional", location)
        self.assertTrue(location.endswith("#link_001-resource_001"))

    def test_identity_save_reports_success_and_keeps_filter_contract(self):
        message = web_app._status_message(
            "/projects/demo/resources?saved_identity=link_001-resource_001"
        )

        self.assertIn("Pertenencia al grupo guardada", message)


if __name__ == "__main__":
    unittest.main()

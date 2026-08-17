import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app


class DocumentMapPageTests(unittest.TestCase):
    def test_document_map_path_is_recognized(self):
        self.assertEqual(
            web_app._project_id_from_document_map_path(
                "/projects/example/document-map"
            ),
            "example",
        )

    def test_page_contains_projected_node_and_local_edit_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir)
            project_dir = projects_dir / "example"
            project_dir.mkdir()
            (project_dir / "project.json").write_text(
                json.dumps({"project_id": "example", "name": "Ejemplo"}),
                encoding="utf-8",
            )
            state = {
                "project_id": "example",
                "nodes": [
                    {
                        "link_id": "node_1",
                        "title": "Nodo uno",
                        "url": "https://test/node",
                        "primary_role": "terminal_case",
                        "is_active": True,
                        "lifecycle_status": "active",
                    }
                ],
                "appearances": [],
                "canonical_resources": [],
                "relations": [],
            }
            with patch.object(web_app, "PROJECTS_DIR", projects_dir), patch.object(
                web_app,
                "resolve_effective_project_state",
                return_value=state,
            ):
                page = web_app._document_map_page("example")

        self.assertIn("Nodo uno", page)
        self.assertIn("Mapa documental editable", page)
        self.assertIn("document-shell", page)
        self.assertIn('role="combobox"', page)
        self.assertIn("document-terminal-suggestions", page)
        self.assertIn("Buscar o seleccionar trámite", page)
        self.assertIn("Cobertura del recurso", page)
        self.assertIn("Abrir recurso", page)
        self.assertIn("method=\"post\"", page)
        self.assertIn("El cambio afecta solo a este trámite", page)

    def test_document_map_resource_route_is_recognized(self):
        self.assertEqual(
            web_app._document_map_resource_route(
                "/projects/example/document-map/resources/node_1/resource_1"
            ),
            ("example", "node_1", "resource_1"),
        )


if __name__ == "__main__":
    unittest.main()

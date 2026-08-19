import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app
from ui.document_map_page import render_document_map_body


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

    def test_single_node_consolidated_resource_has_one_editor_without_coverage(self):
        project = {"project_id": "example", "name": "Ejemplo"}
        appearance = {
            "source_link_id": "node_1",
            "resource_id": "agenda_1",
            "effective_use": "show_as_link",
        }
        duplicate = dict(appearance, resource_id="agenda_2")
        resource = {
            "canonical_resource_key": "canonical:agenda",
            "display_name": "Agenda electrónica",
            "canonical_url": "https://test/agenda",
            "resource_type": "agenda",
            "effective_use": "show_as_link",
            "is_consolidated": True,
            "active_source_nodes": [{"link_id": "node_1", "title": "Nodo uno"}],
            "inactive_source_nodes": [],
            "node_appearances": [appearance, duplicate],
            "appearance_count": 2,
        }
        document_map = {
            "project_id": "example",
            "nodes": [{
                "link_id": "node_1",
                "title": "Nodo uno",
                "url": "https://test/node",
                "is_active": True,
                "resources": [dict(resource, relation_status="active")],
                "summary": {
                    "resource_count": 1,
                    "shared_count": 0,
                    "pending_count": 0,
                    "provisional_count": 0,
                },
            }],
            "resources": {"canonical:agenda": resource},
            "summary": {"terminal_node_count": 1},
        }

        page = render_document_map_body(project, document_map)

        self.assertIn(
            "const selectable = resource.is_consolidated && coverageNodeCount > 1;",
            page,
        )
        self.assertIn("${resourceEdit(resource.node_appearances)}", page)
        self.assertNotIn(
            "resource.node_appearances.map(appearance => resourceEdit(appearance))",
            page,
        )
        self.assertIn('name="resource_id"', page)
        self.assertIn("apariciones equivalentes", page)


if __name__ == "__main__":
    unittest.main()

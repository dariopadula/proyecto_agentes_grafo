import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.json_store import load_json
from core.json_store import save_json
import web_app
import workflows.project_administration as administration
import workflows.project_setup as project_setup


class ProjectAdministrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.projects = self.root / "projects"
        self.outputs = self.root / "outputs"
        self.deleted = self.root / "deleted"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_project_validates_and_does_not_overwrite(self):
        with patch.object(project_setup, "PROJECTS_DIR", self.projects), patch.object(
            project_setup, "OUTPUTS_DIR", self.outputs
        ):
            project_setup.create_project(
                "proyecto_demo", "Proyecto demo",
                "https://example.test/tramites", "funcionario",
            )
            with self.assertRaisesRegex(ValueError, "Ya existe"):
                project_setup.create_project(
                    "proyecto_demo", "Otro nombre",
                    "https://example.test/otra", "funcionario",
                )

        project = load_json(self.projects / "proyecto_demo" / "project.json")
        self.assertEqual(project["name"], "Proyecto demo")

    def test_recoverable_delete_moves_project_and_outputs(self):
        project_dir = self.projects / "demo"
        output_dir = self.outputs / "demo"
        project_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        save_json({"project_id": "demo", "name": "Demo"}, project_dir / "project.json")
        (output_dir / "report.txt").write_text("salida", encoding="utf-8")

        with patch.object(administration, "PROJECTS_DIR", self.projects), patch.object(
            administration, "OUTPUTS_DIR", self.outputs
        ), patch.object(administration, "DELETED_PROJECTS_DIR", self.deleted):
            result = administration.delete_project_recoverably(
                "demo", "demo", "funcionario"
            )

        archive = Path(result["archive_dir"])
        self.assertFalse(project_dir.exists())
        self.assertTrue((archive / "project" / "project.json").exists())
        self.assertTrue((archive / "outputs" / "report.txt").exists())
        self.assertTrue(load_json(archive / "deletion.json")["recoverable"])

    def test_delete_requires_exact_confirmation(self):
        project_dir = self.projects / "demo"
        project_dir.mkdir(parents=True)
        save_json({"project_id": "demo", "name": "Demo"}, project_dir / "project.json")
        with patch.object(administration, "PROJECTS_DIR", self.projects), patch.object(
            administration, "DELETED_PROJECTS_DIR", self.deleted
        ):
            with self.assertRaisesRegex(ValueError, "confirmacion"):
                administration.delete_project_recoverably("demo", "otro", "funcionario")
        self.assertTrue(project_dir.exists())

    def test_projects_page_exposes_create_discover_and_delete(self):
        project_dir = self.projects / "demo"
        project_dir.mkdir(parents=True)
        save_json(
            {"project_id": "demo", "name": "Demo", "start_url": "https://example.test", "status": "draft"},
            project_dir / "project.json",
        )
        with patch.object(web_app, "PROJECTS_DIR", self.projects):
            page = web_app._projects_page()

        self.assertIn("Nuevo proyecto", page)
        self.assertIn('/projects/demo/discover-links', page)
        self.assertIn('/projects/demo/delete', page)
        self.assertIn("Flujo principal", page)
        self.assertIn("Revisión avanzada", page)
        self.assertLess(page.index("Ver mapa documental"), page.index("Revisar casos individuales"))
        self.assertLess(page.index("Revisar casos individuales"), page.index("Ver estado efectivo"))

    def test_existing_project_only_offers_review_not_discovery(self):
        project_dir = self.projects / "demo"
        project_dir.mkdir(parents=True)
        save_json(
            {"project_id": "demo", "name": "Demo", "start_url": "https://example.test", "status": "link_review"},
            project_dir / "project.json",
        )
        save_json(
            {"links": [{"link_id": "link_001", "url": "https://example.test/uno"}]},
            project_dir / "candidate_links.json",
        )
        with patch.object(web_app, "PROJECTS_DIR", self.projects):
            page = web_app._projects_page()

        self.assertIn("Revisar links", page)
        self.assertNotIn('/projects/demo/discover-links', page)

    def test_administration_routes_are_recognized(self):
        self.assertEqual(web_app._project_id_from_discover_path("/projects/demo/discover-links"), "demo")
        self.assertEqual(web_app._project_id_from_delete_path("/projects/demo/delete"), "demo")


if __name__ == "__main__":
    unittest.main()

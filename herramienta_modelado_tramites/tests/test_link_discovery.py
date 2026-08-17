import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.json_store import load_json
from core.json_store import save_json
import workflows.link_discovery as discovery


class LinkDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects = Path(self.temp_dir.name)
        self.project_dir = self.projects / "demo"
        self.project_dir.mkdir()
        save_json(
            {"project_id": "demo", "start_url": "https://tramites.montevideo.gub.uy/buscador_tramites/Demo", "status": "draft"},
            self.project_dir / "project.json",
        )
        save_json({"events": []}, self.project_dir / "change_log.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discovers_all_pages_and_deduplicates_candidates(self):
        start = "https://tramites.montevideo.gub.uy/buscador_tramites/Demo"
        page_two = f"{start}?page=1"
        pages = {
            start: self._html("/tramites-y-tributos/consulta/uno", "Uno", '?page=1'),
            page_two: self._html("/tramites-y-tributos/denuncia/dos", "Dos", None)
                + self._result("/tramites-y-tributos/consulta/uno", "Uno repetido"),
        }
        with patch.object(discovery, "PROJECTS_DIR", self.projects), patch.object(
            discovery, "fetch_page", side_effect=lambda url: pages[url]
        ):
            result = discovery.discover_candidate_links("demo", "funcionario")

        payload = load_json(self.project_dir / "candidate_links.json")
        self.assertEqual(result["pages_scanned"], 2)
        self.assertEqual(result["links_count"], 2)
        self.assertEqual([item["link_id"] for item in payload["links"]], ["link_001", "link_002"])
        self.assertEqual(len(payload["links"][0]["source_page_urls"]), 2)

    def test_secondary_page_failure_is_reported_without_losing_first_page(self):
        start = "https://tramites.montevideo.gub.uy/buscador_tramites/Demo"
        page_two = f"{start}?page=1"

        def fetch(url):
            if url == page_two:
                raise RuntimeError("sin respuesta")
            return self._html("/tramites-y-tributos/solicitud/uno", "Uno", '?page=1')

        with patch.object(discovery, "PROJECTS_DIR", self.projects), patch.object(
            discovery, "fetch_page", side_effect=fetch
        ):
            result = discovery.discover_candidate_links("demo", "funcionario")

        self.assertEqual(result["links_count"], 1)
        self.assertEqual(result["pages_scanned"], 1)
        self.assertEqual(result["page_errors"][0]["url"], page_two)

    @staticmethod
    def _result(href, title):
        return f'<div class="listado-tramites views-row"><div class="views-field-title"><a href="{href}">{title}</a></div></div>'

    def _html(self, href, title, next_href):
        pager = f'<a href="{next_href}">Siguiente</a>' if next_href else ""
        return self._result(href, title) + pager


if __name__ == "__main__":
    unittest.main()

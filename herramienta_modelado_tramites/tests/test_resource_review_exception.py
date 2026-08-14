import tempfile
import unittest
from pathlib import Path

from core.json_store import load_json
from core.json_store import save_json
import workflows.resource_review as resource_review


class ResourceReviewExceptionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_projects_dir = resource_review.PROJECTS_DIR
        resource_review.PROJECTS_DIR = Path(self.temp_dir.name)
        self.project_dir = Path(self.temp_dir.name) / "demo"
        self.project_dir.mkdir()
        save_json(
            {
                "pages": [
                    {
                        "link_id": "node_1",
                        "resources": [
                            {
                                "resource_id": "resource_1",
                                "url": "https://example.test/agenda",
                                "title": "Agenda",
                                "resource_type": "agenda",
                            }
                        ],
                        "discarded_resources": [],
                    }
                ]
            },
            self.project_dir / "node_resources.json",
        )
        save_json(
            {
                "project_id": "demo",
                "review_status": "complete",
                "decisions": [
                    {
                        "decision_id": "node_1::resource_1",
                        "source_link_id": "node_1",
                        "resource_id": "resource_1",
                        "use": "show_as_link",
                        "scope": "shared",
                        "decision_source": "auxiliary_group",
                        "source_group_id": "agenda_001",
                        "canonical_resource_id": "agenda_canonical_001",
                        "canonical_url": "https://example.test/agenda-canonica",
                        "inherited": True,
                    }
                ],
            },
            self.project_dir / "resource_review.json",
        )
        save_json({"events": []}, self.project_dir / "change_log.json")

    def tearDown(self):
        resource_review.PROJECTS_DIR = self.original_projects_dir
        self.temp_dir.cleanup()

    def test_editing_inherited_decision_creates_explicit_exception(self):
        resource_review.save_resource_decision(
            project_id="demo",
            source_link_id="node_1",
            resource_id="resource_1",
            use="process_as_context",
            scope="node_only",
            notes="Excepción",
            actor="funcionario",
        )

        payload = load_json(self.project_dir / "resource_review.json")
        decision = payload["decisions"][0]
        self.assertEqual(decision["decision_source"], "individual")
        self.assertTrue(decision["overrides_group"])
        self.assertEqual(
            decision["overridden_group_id"],
            "agenda_001",
        )
        self.assertEqual(decision["canonical_resource_id"], "agenda_canonical_001")
        self.assertEqual(
            decision["canonical_url"],
            "https://example.test/agenda-canonica",
        )


if __name__ == "__main__":
    unittest.main()

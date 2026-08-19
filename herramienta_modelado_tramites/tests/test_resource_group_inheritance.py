import tempfile
import unittest
from pathlib import Path

from core.json_store import load_json
from core.json_store import save_json
import workflows.resource_group_inheritance as inheritance


class ResourceGroupInheritanceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_projects_dir = inheritance.PROJECTS_DIR
        inheritance.PROJECTS_DIR = Path(self.temp_dir.name)
        self.project_dir = Path(self.temp_dir.name) / "demo"
        self.project_dir.mkdir()
        save_json({"events": []}, self.project_dir / "change_log.json")

    def tearDown(self):
        inheritance.PROJECTS_DIR = self.original_projects_dir
        self.temp_dir.cleanup()

    def test_restores_current_auxiliary_group_decision(self):
        self._save_exception("agenda_001")
        save_json(
            {
                "appearances": [
                    {
                        "appearance_id": "node_1::resource_1",
                        "source_node_id": "node_1",
                        "resource_id": "resource_1",
                        "detected_url": "https://example.test/agenda",
                        "label": "Agenda",
                        "detected_resource_type": "agenda",
                    }
                ],
                "agenda_candidates": [
                    {
                        "group_id": "agenda_001",
                        "appearance_ids": ["node_1::resource_1"],
                    }
                ],
            },
            self.project_dir / "auxiliary_link_analysis.json",
        )
        save_json(
            {
                "decisions": [
                    {
                        "group_id": "agenda_001",
                        "appearance_ids": ["node_1::resource_1"],
                        "default_use": "show_as_link",
                        "scope": "shared",
                        "selected_canonical_url": "https://example.test/agenda",
                        "notes": "Decisión vigente",
                    }
                ]
            },
            self.project_dir / "auxiliary_link_group_review.json",
        )

        restored = inheritance.restore_resource_group_inheritance(
            "demo", "node_1", "resource_1", "funcionario"
        )

        self.assertEqual(restored["use"], "show_as_link")
        self.assertEqual(restored["decision_source"], "auxiliary_group")
        self.assertNotIn("overrides_group", restored)
        event = load_json(self.project_dir / "change_log.json")["events"][0]
        self.assertEqual(event["action"], "restore_resource_group_inheritance")

    def test_restores_current_pdf_family_decision_and_shared_scope(self):
        self._save_exception("pdf_family_001")
        save_json(
            {
                "appearances": [
                    {
                        "appearance_id": "node_1::resource_1",
                        "source_node_id": "node_1",
                        "resource_id": "resource_1",
                        "detected_url": "https://example.test/one.pdf",
                        "label": "Documento",
                    },
                    {
                        "appearance_id": "node_2::resource_2",
                        "source_node_id": "node_2",
                        "resource_id": "resource_2",
                        "detected_url": "https://example.test/two.pdf",
                        "label": "Documento",
                    },
                ],
                "proposed_groups": [
                    {
                        "group_id": "pdf_family_001",
                        "appearance_ids": [
                            "node_1::resource_1",
                            "node_2::resource_2",
                        ],
                    }
                ],
            },
            self.project_dir / "pdf_analysis.json",
        )
        save_json(
            {
                "family_decisions": [
                    {
                        "family_id": "pdf_family_001",
                        "appearance_ids": [
                            "node_1::resource_1",
                            "node_2::resource_2",
                        ],
                        "default_use": "process_as_context",
                        "selected_canonical_url": "https://example.test/one.pdf",
                        "notes": "Familia vigente",
                    }
                ],
                "decisions": [],
            },
            self.project_dir / "pdf_group_review.json",
        )

        restored = inheritance.restore_resource_group_inheritance(
            "demo", "node_1", "resource_1", "funcionario"
        )

        self.assertEqual(restored["use"], "process_as_context")
        self.assertEqual(restored["scope"], "shared")
        self.assertEqual(restored["decision_source"], "pdf_group")

    def test_rejects_group_decision_with_changed_membership(self):
        self._save_exception("agenda_001")
        save_json(
            {
                "appearances": [],
                "agenda_candidates": [
                    {
                        "group_id": "agenda_001",
                        "appearance_ids": [
                            "node_1::resource_1",
                            "node_2::resource_2",
                        ],
                    }
                ],
            },
            self.project_dir / "auxiliary_link_analysis.json",
        )
        save_json(
            {
                "decisions": [
                    {
                        "group_id": "agenda_001",
                        "appearance_ids": ["node_1::resource_1"],
                    }
                ]
            },
            self.project_dir / "auxiliary_link_group_review.json",
        )

        with self.assertRaisesRegex(ValueError, "decisión vigente"):
            inheritance.restore_resource_group_inheritance(
                "demo", "node_1", "resource_1", "funcionario"
            )

        decision = load_json(self.project_dir / "resource_review.json")[
            "decisions"
        ][0]
        self.assertTrue(decision["overrides_group"])

    def _save_exception(self, group_id: str) -> None:
        save_json(
            {
                "project_id": "demo",
                "review_status": "complete",
                "decisions": [
                    {
                        "decision_id": "node_1::resource_1",
                        "source_link_id": "node_1",
                        "resource_id": "resource_1",
                        "use": "discard",
                        "scope": "node_only",
                        "decision_source": "individual",
                        "overrides_group": True,
                        "overridden_group_id": group_id,
                        "source_group_id": group_id,
                    }
                ],
            },
            self.project_dir / "resource_review.json",
        )


if __name__ == "__main__":
    unittest.main()

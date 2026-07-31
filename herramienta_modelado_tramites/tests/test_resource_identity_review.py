import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.resource_identity_review import save_resource_identity_decision


class ResourceIdentityReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name)
        self.project_dir = self.projects_dir / "demo"
        self.project_dir.mkdir()
        _write(
            self.project_dir / "pdf_analysis.json",
            {
                "project_id": "demo",
                "appearances": [
                    {
                        "appearance_id": "node_1::resource_1",
                        "source_node_id": "node_1",
                        "resource_id": "resource_1",
                        "label": "Documento",
                        "detected_url": "https://example.test/doc.pdf",
                    }
                ],
                "proposed_groups": [
                    {
                        "group_id": "pdf_family_001",
                        "appearance_ids": [],
                        "evidence": {"appearance_count": 0},
                        "verification": {"status": "complete"},
                        "proposed_canonical_resource": {
                            "display_name": "Familia existente"
                        },
                    }
                ],
            },
        )
        _write(self.project_dir / "change_log.json", {"events": []})

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_assigns_candidate_to_existing_family_and_resets_verification(self):
        with patch(
            "workflows.resource_identity_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            save_resource_identity_decision(
                "demo",
                "node_1::resource_1",
                "assign_existing",
                "pdf_family_001",
                "candidate_verify",
                "",
                "Coincide el documento",
                "tester",
            )

        analysis = _read(self.project_dir / "pdf_analysis.json")
        family = analysis["proposed_groups"][0]
        self.assertEqual(family["appearance_ids"], ["node_1::resource_1"])
        self.assertEqual(family["verification"]["status"], "not_started")

    def test_creates_new_family_and_persists_its_identifier(self):
        with patch(
            "workflows.resource_identity_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            decision = save_resource_identity_decision(
                "demo",
                "node_1::resource_1",
                "create_family",
                "",
                "candidate_verify",
                "Nueva familia",
                "No coincide con las existentes",
                "tester",
            )

        review = _read(self.project_dir / "resource_identity_review.json")
        self.assertTrue(decision["target_family_id"].startswith("pdf_manual_"))
        self.assertEqual(
            review["decisions"][0]["target_family_id"],
            decision["target_family_id"],
        )


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.pdf_analysis import _reconcile_manual_family_decision
from workflows.pdf_group_review import save_pdf_family_decision
from workflows.pdf_group_review import save_pdf_partition_decision


class PdfGroupReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name)
        self.project_dir = self.projects_dir / "demo"
        self.project_dir.mkdir()
        self.url_one = "https://example.test/one.pdf"
        self.url_two = "https://example.test/two.pdf"
        _write_json(
            self.project_dir / "pdf_analysis.json",
            {
                "generated_at": "2026-07-29T12:00:00-03:00",
                "appearances": [
                    {"appearance_id": "node_1::pdf_1", "detected_url": self.url_one},
                    {"appearance_id": "node_2::pdf_2", "detected_url": self.url_two},
                ],
                "proposed_groups": [
                    {
                        "group_id": "pdf_family_001",
                        "appearance_ids": ["node_1::pdf_1", "node_2::pdf_2"],
                        "verification": {
                            "partitions": [
                                {
                                    "partition_id": "pdf_family_001_part_001",
                                    "appearance_ids": [
                                        "node_1::pdf_1",
                                        "node_2::pdf_2",
                                    ],
                                }
                            ]
                        },
                    }
                ],
            },
        )
        _write_json(self.project_dir / "change_log.json", {"events": []})

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_decision_is_saved_separately_from_analysis(self):
        analysis_before = (self.project_dir / "pdf_analysis.json").read_text(
            encoding="utf-8"
        )
        with patch(
            "workflows.pdf_group_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            decision = save_pdf_partition_decision(
                project_id="demo",
                family_id="pdf_family_001",
                partition_id="pdf_family_001_part_001",
                identity_decision="confirmed_same",
                default_use="process_as_context",
                selected_canonical_url=self.url_one,
                display_name="Documento compartido",
                notes="Revisado",
                actor="tester",
            )

        review = _read_json(self.project_dir / "pdf_group_review.json")
        self.assertEqual(decision["identity_decision"], "confirmed_same")
        self.assertEqual(review["review_status"], "complete")
        self.assertEqual(len(review["decisions"]), 1)
        self.assertEqual(
            analysis_before,
            (self.project_dir / "pdf_analysis.json").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            _read_json(self.project_dir / "change_log.json")["events"][0][
                "target_type"
            ],
            "pdf_group",
        )

    def test_canonical_url_must_belong_to_group(self):
        with patch(
            "workflows.pdf_group_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            with self.assertRaisesRegex(ValueError, "URL canónica"):
                save_pdf_partition_decision(
                    project_id="demo",
                    family_id="pdf_family_001",
                    partition_id="pdf_family_001_part_001",
                    identity_decision="confirmed_same",
                    default_use="show_as_link",
                    selected_canonical_url="https://other.test/file.pdf",
                    display_name="Documento",
                    notes="",
                    actor="tester",
                )

    def test_family_can_be_confirmed_before_verification(self):
        with patch(
            "workflows.pdf_group_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            decision = save_pdf_family_decision(
                project_id="demo",
                family_id="pdf_family_001",
                default_use="process_as_context",
                selected_canonical_url=self.url_one,
                display_name="Documento conocido",
                notes="Confirmado por conocimiento del trámite",
                actor="tester",
            )

        review = _read_json(self.project_dir / "pdf_group_review.json")
        self.assertEqual(
            decision["identity_decision"],
            "confirmed_same_manually",
        )
        self.assertEqual(
            review["family_decisions"][0]["verification_reconciliation"],
            "pending",
        )

    def test_consistent_verification_inherits_family_decision(self):
        with patch(
            "workflows.pdf_group_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            save_pdf_family_decision(
                project_id="demo",
                family_id="pdf_family_001",
                default_use="process_as_context",
                selected_canonical_url=self.url_one,
                display_name="Documento conocido",
                notes="",
                actor="tester",
            )

        family = {
            "group_id": "pdf_family_001",
            "verification": {
                "status": "complete",
                "all_appearances_same": True,
                "partitions": [
                    {"partition_id": "pdf_family_001_part_001"}
                ],
            },
        }
        _reconcile_manual_family_decision(self.project_dir, family)

        review = _read_json(self.project_dir / "pdf_group_review.json")
        inherited = review["decisions"][0]
        self.assertEqual(
            inherited["decision_source"],
            "inherited_from_family",
        )
        self.assertEqual(
            review["family_decisions"][0]["verification_reconciliation"],
            "consistent",
        )

    def test_multiple_partitions_do_not_inherit_family_decision(self):
        with patch(
            "workflows.pdf_group_review.PROJECTS_DIR",
            self.projects_dir,
        ):
            save_pdf_family_decision(
                project_id="demo",
                family_id="pdf_family_001",
                default_use="show_as_link",
                selected_canonical_url=self.url_one,
                display_name="Documento conocido",
                notes="",
                actor="tester",
            )

        family = {
            "group_id": "pdf_family_001",
            "verification": {
                "status": "complete",
                "all_appearances_same": False,
                "partitions": [
                    {"partition_id": "part_1"},
                    {"partition_id": "part_2"},
                ],
            },
        }
        _reconcile_manual_family_decision(self.project_dir, family)

        review = _read_json(self.project_dir / "pdf_group_review.json")
        self.assertEqual(review.get("decisions", []), [])
        self.assertEqual(
            review["family_decisions"][0]["verification_reconciliation"],
            "conflict",
        )


def _write_json(path: Path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

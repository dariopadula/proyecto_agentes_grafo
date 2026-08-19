import tempfile
import unittest
from pathlib import Path

from core.json_store import load_json
from core.json_store import save_json
import workflows.auxiliary_link_group_review as group_review
import workflows.resource_review as resource_review


class AuxiliaryLinkGroupReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_projects_dir = group_review.PROJECTS_DIR
        self.original_resource_projects_dir = resource_review.PROJECTS_DIR
        group_review.PROJECTS_DIR = Path(self.temp_dir.name)
        resource_review.PROJECTS_DIR = Path(self.temp_dir.name)
        self.project_dir = Path(self.temp_dir.name) / "demo"
        self.project_dir.mkdir()
        save_json(_analysis_fixture(), self.project_dir / "auxiliary_link_analysis.json")
        save_json(
            {
                "project_id": "demo",
                "review_status": "in_progress",
                "updated_at": "earlier",
                "decisions": [
                    {
                        "decision_id": "node_2::resource_2",
                        "source_link_id": "node_2",
                        "resource_id": "resource_2",
                        "use": "process_as_context",
                        "scope": "node_only",
                        "reviewed_by": "funcionario",
                    }
                ],
            },
            self.project_dir / "resource_review.json",
        )
        save_json(
            {"events": []},
            self.project_dir / "change_log.json",
        )
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
                    },
                    {
                        "link_id": "node_2",
                        "resources": [
                            {
                                "resource_id": "resource_2",
                                "url": "https://example.test/agenda",
                                "title": "Agenda",
                                "resource_type": "agenda",
                            }
                        ],
                        "discarded_resources": [],
                    },
                ]
            },
            self.project_dir / "node_resources.json",
        )

    def tearDown(self):
        group_review.PROJECTS_DIR = self.original_projects_dir
        resource_review.PROJECTS_DIR = self.original_resource_projects_dir
        self.temp_dir.cleanup()

    def test_group_decision_overwrites_legacy_individual_decisions(self):
        decision = group_review.save_auxiliary_group_decision(
            project_id="demo",
            group_id="agenda_001",
            identity_decision="confirmed_same",
            default_use="show_as_link",
            scope="shared",
            selected_canonical_url="https://example.test/agenda",
            display_name="Agenda común",
            notes="Decisión agrupada",
            actor="funcionario",
        )

        self.assertEqual(
            decision["materialization"]["applied_appearance_ids"],
            ["node_1::resource_1", "node_2::resource_2"],
        )
        self.assertEqual(
            decision["materialization"][
                "preserved_individual_exception_ids"
            ],
            [],
        )
        resource_review = load_json(
            self.project_dir / "resource_review.json"
        )
        inherited = next(
            item
            for item in resource_review["decisions"]
            if item["decision_id"] == "node_1::resource_1"
        )
        second_inherited = next(
            item
            for item in resource_review["decisions"]
            if item["decision_id"] == "node_2::resource_2"
        )
        self.assertEqual(inherited["decision_source"], "auxiliary_group")
        self.assertEqual(inherited["source_group_id"], "agenda_001")
        self.assertTrue(inherited["inherited"])
        self.assertEqual(
            second_inherited["decision_source"],
            "auxiliary_group",
        )

    def test_explicit_individual_exception_is_preserved(self):
        resource_review_path = self.project_dir / "resource_review.json"
        resource_review = load_json(resource_review_path)
        resource_review["decisions"][0]["overrides_group"] = True
        resource_review["decisions"][0]["decision_source"] = "individual"
        save_json(resource_review, resource_review_path)

        decision = group_review.save_auxiliary_group_decision(
            project_id="demo",
            group_id="agenda_001",
            identity_decision="confirmed_same",
            default_use="show_as_link",
            scope="shared",
            selected_canonical_url="https://example.test/agenda",
            display_name="Agenda común",
            notes="",
            actor="funcionario",
        )

        self.assertEqual(
            decision["materialization"][
                "preserved_individual_exception_ids"
            ],
            ["node_2::resource_2"],
        )

    def test_updating_group_updates_its_inherited_decisions(self):
        arguments = {
            "project_id": "demo",
            "group_id": "agenda_001",
            "identity_decision": "confirmed_same",
            "default_use": "show_as_link",
            "scope": "shared",
            "selected_canonical_url": "https://example.test/agenda",
            "display_name": "Agenda común",
            "notes": "",
            "actor": "funcionario",
        }
        group_review.save_auxiliary_group_decision(**arguments)
        arguments["default_use"] = "review_later"
        group_review.save_auxiliary_group_decision(**arguments)

        resource_review = load_json(
            self.project_dir / "resource_review.json"
        )
        inherited = next(
            item
            for item in resource_review["decisions"]
            if item["decision_id"] == "node_1::resource_1"
        )
        self.assertEqual(inherited["use"], "review_later")

    def test_repeated_individual_edits_remain_protected_from_group(self):
        arguments = {
            "project_id": "demo",
            "group_id": "agenda_001",
            "identity_decision": "confirmed_same",
            "default_use": "show_as_link",
            "scope": "shared",
            "selected_canonical_url": "https://example.test/agenda",
            "display_name": "Agenda común",
            "notes": "",
            "actor": "funcionario",
        }
        group_review.save_auxiliary_group_decision(**arguments)
        for use in ("process_as_context", "discard"):
            resource_review.save_resource_decision(
                project_id="demo",
                source_link_id="node_1",
                resource_id="resource_1",
                use=use,
                scope="node_only",
                notes="Excepción repetida",
                actor="funcionario",
            )

        arguments["default_use"] = "review_later"
        decision = group_review.save_auxiliary_group_decision(**arguments)

        self.assertEqual(
            decision["materialization"]["preserved_individual_exception_ids"],
            ["node_1::resource_1"],
        )
        payload = load_json(self.project_dir / "resource_review.json")
        exception = next(
            item
            for item in payload["decisions"]
            if item["decision_id"] == "node_1::resource_1"
        )
        self.assertEqual(exception["use"], "discard")
        self.assertTrue(exception["overrides_group"])


def _analysis_fixture():
    appearances = [
        {
            "appearance_id": "node_1::resource_1",
            "source_node_id": "node_1",
            "resource_id": "resource_1",
            "detected_url": "https://example.test/agenda",
            "candidate_canonical_url": "https://example.test/agenda",
            "label": "Agenda",
            "detected_resource_type": "agenda",
            "filter_status": "reviewable",
        },
        {
            "appearance_id": "node_2::resource_2",
            "source_node_id": "node_2",
            "resource_id": "resource_2",
            "detected_url": "https://example.test/agenda",
            "candidate_canonical_url": "https://example.test/agenda",
            "label": "Agenda",
            "detected_resource_type": "agenda",
            "filter_status": "reviewable",
        },
    ]
    return {
        "generated_at": "2026-07-30T00:00:00-03:00",
        "appearances": appearances,
        "agenda_candidates": [
            {
                "group_id": "agenda_001",
                "appearance_ids": [
                    "node_1::resource_1",
                    "node_2::resource_2",
                ],
            }
        ],
        "normalized_equivalence_candidates": [],
        "exact_url_groups": [],
    }


if __name__ == "__main__":
    unittest.main()

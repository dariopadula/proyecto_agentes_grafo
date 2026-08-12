import json
import tempfile
import unittest
from pathlib import Path

from workflows.effective_project_state import resolve_effective_project_state


class EffectiveProjectStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name)
        self.project_dir = self.projects_dir / "example"
        self.project_dir.mkdir()
        self._write(
            "candidate_links.json",
            {
                "links": [
                    {"link_id": "node_1", "url": "https://test/1", "title": "Uno"},
                    {"link_id": "node_2", "url": "https://test/2", "title": "Dos"},
                    {"link_id": "node_3", "url": "https://test/3", "title": "Fuera"},
                ]
            },
        )
        self._write(
            "human_review.json",
            {
                "decisions": [
                    {"link_id": "node_1", "primary_role": "terminal_case"},
                    {"link_id": "node_2", "primary_role": "terminal_case"},
                    {"link_id": "node_3", "primary_role": "discarded"},
                ]
            },
        )
        self._write(
            "node_resources.json",
            {
                "pages": [
                    {
                        "link_id": "node_1",
                        "status": "ok",
                        "resources": [self._resource("resource_1", "https://test/a.pdf")],
                    },
                    {
                        "link_id": "node_2",
                        "status": "ok",
                        "resources": [self._resource("resource_2", "https://test/b.pdf")],
                    },
                ]
            },
        )
        self._write(
            "resource_review.json",
            {
                "decisions": [
                    self._decision("node_1", "resource_1"),
                    self._decision("node_2", "resource_2"),
                ]
            },
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_groups_appearances_and_derives_shared_scope(self):
        state = resolve_effective_project_state("example", self.projects_dir)

        self.assertEqual(state["summary"]["active_node_count"], 2)
        self.assertEqual(state["summary"]["appearance_count"], 2)
        self.assertEqual(state["summary"]["canonical_resource_count"], 1)
        resource = state["canonical_resources"][0]
        self.assertEqual(resource["effective_scope"], "shared")
        self.assertEqual(resource["active_source_link_ids"], ["node_1", "node_2"])
        self.assertEqual(resource["effective_use"], "process_as_context")

    def test_lifecycle_overlay_changes_relations_without_losing_evidence(self):
        self._write(
            "lifecycle_review.json",
            {"node_states": [{"link_id": "node_1", "status": "inactive"}]},
        )

        state = resolve_effective_project_state("example", self.projects_dir)

        self.assertEqual(state["summary"]["appearance_count"], 2)
        resource = state["canonical_resources"][0]
        self.assertEqual(resource["effective_scope"], "node_only")
        self.assertEqual(resource["active_source_link_ids"], ["node_2"])
        relation_statuses = {
            item["source_link_id"]: item["status"] for item in state["relations"]
        }
        self.assertEqual(relation_statuses, {"node_1": "inactive", "node_2": "active"})

    def test_resource_becomes_orphaned_when_all_source_nodes_are_inactive(self):
        self._write(
            "lifecycle_review.json",
            {
                "node_states": [
                    {"link_id": "node_1", "status": "inactive"},
                    {"link_id": "node_2", "status": "inactive"},
                ]
            },
        )

        state = resolve_effective_project_state("example", self.projects_dir)

        resource = state["canonical_resources"][0]
        self.assertEqual(resource["lifecycle_status"], "orphaned")
        self.assertEqual(resource["effective_scope"], "orphaned")
        self.assertEqual(state["summary"]["orphaned_resource_count"], 1)

    def _resource(self, resource_id, url):
        return {
            "resource_id": resource_id,
            "url": url,
            "title": "Documento",
            "resource_type": "pdf",
        }

    def _decision(self, node_id, resource_id):
        return {
            "decision_id": f"{node_id}::{resource_id}",
            "source_link_id": node_id,
            "resource_id": resource_id,
            "canonical_url": "https://test/canonical.pdf",
            "canonical_resource_id": "pdf_family_001",
            "use": "process_as_context",
            "scope": "node_only",
            "decision_source": "pdf_group",
        }

    def _write(self, name, payload):
        (self.project_dir / name).write_text(
            json.dumps(payload),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()

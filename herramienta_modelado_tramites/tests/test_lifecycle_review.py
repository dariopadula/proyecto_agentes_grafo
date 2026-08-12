import json
import tempfile
import unittest
from pathlib import Path

from workflows.effective_project_state import resolve_effective_project_state
from workflows.lifecycle_review import node_lifecycle_impact
from workflows.lifecycle_review import save_node_lifecycle_status


class LifecycleReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name)
        self.project_dir = self.projects_dir / "example"
        self.project_dir.mkdir()
        self._write("candidate_links.json", {"links": [
            {"link_id": "node_1", "title": "Uno", "url": "https://test/1"},
            {"link_id": "node_2", "title": "Dos", "url": "https://test/2"},
        ]})
        self._write("human_review.json", {"decisions": [
            {"link_id": "node_1", "primary_role": "terminal_case"},
            {"link_id": "node_2", "primary_role": "terminal_case"},
        ]})
        self._write("node_resources.json", {"pages": [
            {"link_id": "node_1", "resources": [self._resource("r1")]},
            {"link_id": "node_2", "resources": [self._resource("r2")]},
        ]})
        self._write("resource_review.json", {"decisions": [
            self._decision("node_1", "r1"), self._decision("node_2", "r2")
        ]})
        self._write("change_log.json", {"project_id": "example", "events": []})

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_deactivation_is_persisted_and_reversible(self):
        save_node_lifecycle_status(
            "example", "node_1", "inactive", "Fuera temporalmente", "tester",
            self.projects_dir,
        )
        inactive = resolve_effective_project_state("example", self.projects_dir)
        self.assertEqual(inactive["summary"]["active_node_count"], 1)
        self.assertEqual(inactive["canonical_resources"][0]["effective_scope"], "node_only")

        save_node_lifecycle_status(
            "example", "node_1", "active", "Reincorporado", "tester",
            self.projects_dir,
        )
        active = resolve_effective_project_state("example", self.projects_dir)
        self.assertEqual(active["summary"]["active_node_count"], 2)
        self.assertEqual(active["canonical_resources"][0]["effective_scope"], "shared")
        lifecycle = json.loads((self.project_dir / "lifecycle_review.json").read_text())
        self.assertEqual(lifecycle["node_states"][0]["status"], "active")
        change_log = json.loads((self.project_dir / "change_log.json").read_text())
        self.assertEqual([e["action"] for e in change_log["events"]], [
            "deactivate_node", "reactivate_node"
        ])

    def test_preview_preserves_shared_resource(self):
        state = resolve_effective_project_state("example", self.projects_dir)
        impact = node_lifecycle_impact(state, "node_1")
        self.assertEqual(impact["relation_count"], 1)
        self.assertEqual(impact["orphaned_resource_count"], 0)
        self.assertEqual(impact["still_used_resource_count"], 1)

    def _resource(self, resource_id):
        return {"resource_id": resource_id, "url": f"https://test/{resource_id}.pdf", "title": "PDF", "resource_type": "pdf"}

    def _decision(self, node_id, resource_id):
        return {"decision_id": f"{node_id}::{resource_id}", "canonical_resource_id": "family_1", "canonical_url": "https://test/c.pdf", "use": "process_as_context", "decision_source": "pdf_group"}

    def _write(self, name, payload):
        (self.project_dir / name).write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

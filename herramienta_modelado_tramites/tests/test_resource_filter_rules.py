import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.resource_filter_rules import apply_resource_filter_rules
from workflows.resource_filter_rules import save_resource_filter_configuration


class ResourceFilterRuleTests(unittest.TestCase):
    def test_project_can_disable_defaults_and_add_rule_before_grouping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir)
            (projects_dir / "demo").mkdir()
            with patch(
                "workflows.resource_filter_rules.PROJECTS_DIR",
                projects_dir,
            ):
                payload = save_resource_filter_configuration(
                    project_id="demo",
                    enabled_rule_ids=["rule_001"],
                    match_type="url_contains",
                    pattern="/ignorar/",
                    reason="No pertenece al trámite",
                )

            self.assertTrue(payload["rules"][0]["enabled"])
            self.assertFalse(payload["rules"][1]["enabled"])
            self.assertEqual(payload["rules"][-1]["pattern"], "/ignorar/")
            kept, discarded = apply_resource_filter_rules(
                [
                    {"url": "https://example.test/ignorar/recurso"},
                    {"url": "https://example.test/util"},
                ],
                payload,
            )
            self.assertEqual(len(kept), 1)
            self.assertEqual(discarded[0]["discard_rule_id"], "rule_004")


if __name__ == "__main__":
    unittest.main()

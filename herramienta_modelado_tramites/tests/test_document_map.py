import unittest

from workflows.document_map import build_document_map


class DocumentMapTests(unittest.TestCase):
    def test_builds_node_summary_without_counting_canonical_appearances_twice(self):
        view = build_document_map(self._state())

        self.assertEqual(view["summary"]["terminal_node_count"], 2)
        self.assertEqual(view["summary"]["shared_resource_count"], 1)
        node = next(item for item in view["nodes"] if item["link_id"] == "node_1")
        self.assertEqual(node["summary"]["resource_count"], 3)
        self.assertEqual(node["summary"]["context_count"], 1)
        self.assertEqual(node["summary"]["link_count"], 1)
        self.assertEqual(node["summary"]["discarded_count"], 1)
        self.assertEqual(node["summary"]["shared_count"], 1)
        self.assertEqual(node["summary"]["consolidated_count"], 1)
        self.assertEqual(node["summary"]["provisional_count"], 1)
        shared = next(
            item for item in node["resources"]
            if item["canonical_resource_key"] == "canonical:shared_pdf"
        )
        self.assertEqual(len(shared["node_appearances"]), 1)
        self.assertEqual(shared["node_appearances"][0]["resource_id"], "pdf_1")

    def test_exposes_active_and_inactive_coverage_for_canonical_resource(self):
        view = build_document_map(self._state())

        resource = view["resources"]["canonical:shared_pdf"]
        self.assertEqual(
            {item["link_id"] for item in resource["active_source_nodes"]},
            {"node_1", "node_2"},
        )
        self.assertEqual(
            [item["link_id"] for item in resource["inactive_source_nodes"]],
            ["node_3"],
        )
        self.assertEqual(resource["appearance_count"], 3)

    def test_keeps_non_terminal_nodes_out_of_general_map(self):
        view = build_document_map(self._state())

        self.assertEqual(
            {item["link_id"] for item in view["nodes"]},
            {"node_1", "node_2"},
        )

    def _state(self):
        nodes = [
            self._node("node_1", "Uno", "terminal_case", True),
            self._node("node_2", "Dos", "terminal_case", True),
            self._node("node_3", "Tres", "auxiliary_info", False),
        ]
        appearances = [
            self._appearance("node_1::pdf_1", "node_1", "pdf", "canonical:shared_pdf", "process_as_context"),
            self._appearance("node_2::pdf_2", "node_2", "pdf", "canonical:shared_pdf", "process_as_context"),
            self._appearance("node_3::pdf_3", "node_3", "pdf", "canonical:shared_pdf", "process_as_context", False),
            self._appearance("node_1::agenda", "node_1", "agenda", "appearance:node_1::agenda", "show_as_link"),
            self._appearance("node_1::discarded", "node_1", "link", "appearance:node_1::discarded", "discard"),
        ]
        resources = [
            self._resource("canonical:shared_pdf", "Patologías", "pdf", "process_as_context", [item["appearance_id"] for item in appearances[:3]], ["node_1", "node_2"]),
            self._resource("appearance:node_1::agenda", "Agenda", "agenda", "show_as_link", ["node_1::agenda"], ["node_1"]),
            self._resource("appearance:node_1::discarded", "Ruido", "link", "discard", ["node_1::discarded"], ["node_1"]),
        ]
        relations = [
            self._relation(item["appearance_id"], item["source_link_id"], item["canonical_resource_key"], "active" if item["relation_active"] else "inactive")
            for item in appearances
        ]
        return {
            "project_id": "example",
            "nodes": nodes,
            "appearances": appearances,
            "canonical_resources": resources,
            "relations": relations,
        }

    def _node(self, link_id, title, role, active):
        return {
            "link_id": link_id,
            "title": title,
            "url": f"https://test/{link_id}",
            "primary_role": role,
            "is_active": active,
            "lifecycle_status": "active" if active else "inactive",
        }

    def _appearance(self, appearance_id, node_id, resource_type, key, use, active=True):
        return {
            "appearance_id": appearance_id,
            "source_link_id": node_id,
            "resource_id": appearance_id.split("::", 1)[1],
            "resource_type": resource_type,
            "canonical_resource_key": key,
            "effective_use": use,
            "relation_active": active,
            "title": appearance_id,
            "url": f"https://test/{appearance_id}",
        }

    def _resource(self, key, name, resource_type, use, appearances, active_nodes):
        return {
            "canonical_resource_key": key,
            "display_name": name,
            "canonical_url": "https://test/resource",
            "resource_type": resource_type,
            "effective_use": use,
            "effective_scope": "shared" if len(active_nodes) > 1 else "node_only",
            "lifecycle_status": "active",
            "appearance_ids": appearances,
            "active_source_link_ids": active_nodes,
            "has_conflicting_uses": False,
        }

    def _relation(self, appearance_id, node_id, key, status):
        return {
            "relation_id": appearance_id,
            "appearance_id": appearance_id,
            "source_link_id": node_id,
            "canonical_resource_key": key,
            "status": status,
        }


if __name__ == "__main__":
    unittest.main()

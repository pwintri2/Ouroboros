import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSharePointPnPAdapter(unittest.TestCase):
    def setUp(self):
        self.previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="sharepoint-adapter-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        if self.previous_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.previous_workspace

    def test_fixture_sites_and_permission_analysis(self):
        from controller.sharepoint_pnp_adapter import SharePointPnPAdapter

        adapter = SharePointPnPAdapter(
            fixtures={
                "sites": [
                    {
                        "id": "site-1",
                        "displayName": "Project X",
                        "webUrl": "https://contoso.sharepoint.com/sites/project-x",
                        "uniquePermissions": True,
                        "externalSharing": "Anyone",
                        "permissions": [{"role": "Owner"}],
                    }
                ]
            }
        )
        sites = adapter.list_site_collections()
        self.assertEqual(sites["status"], "success")
        self.assertEqual(len(sites["records_11d"][0]["11d"]["vector"]), 11)

        report = adapter.analyze_permissions()
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["review_count"], 1)
        self.assertTrue(report["findings"][0]["unique_permissions"])

    def test_workflow_trigger_is_approval_gated_and_non_executing(self):
        from controller.sharepoint_pnp_adapter import SharePointPnPAdapter

        adapter = SharePointPnPAdapter()
        blocked = adapter.workflow_trigger_example("https://example/sites/x", "list-1", approval="")
        self.assertEqual(blocked["status"], "blocked")
        approved = adapter.workflow_trigger_example("https://example/sites/x", "list-1", approval="Akkoord")
        self.assertEqual(approved["status"], "approval_recorded")
        self.assertFalse(approved["executed"])


if __name__ == "__main__":
    unittest.main()

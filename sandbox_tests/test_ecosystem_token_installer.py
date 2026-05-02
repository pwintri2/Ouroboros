import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEcosystemTokenInstaller(unittest.TestCase):
    def test_installs_google_token_without_printing_secret(self):
        with tempfile.TemporaryDirectory(prefix="token-installer-") as tmp:
            root = Path(tmp)
            source = root / "token.json"
            source.write_text(json.dumps({"access_token": "super-secret-token", "scopes": ["drive.readonly"]}), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/install_ecosystem_token.py",
                    "--provider",
                    "google",
                    "--token-file",
                    str(source),
                    "--workspace",
                    str(root),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("super-secret-token", proc.stdout)
            target = root / ".secrets" / "google_workspace_token.json"
            self.assertTrue(target.exists())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["access_token"], "super-secret-token")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_token_eater_imports_notepad_style_paste(self):
        from scripts.token_eater import eat_pasted_text

        with tempfile.TemporaryDirectory(prefix="token-eater-paste-") as tmp:
            text = """Google -->
ya29.fake-google-token

Microsoft -->
eyJ.fake-ms-token
"""
            result = eat_pasted_text(workspace=tmp, pasted_text=text)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["imported_count"], 2)
            google = Path(tmp) / ".secrets" / "google_workspace_token.json"
            microsoft = Path(tmp) / ".secrets" / "microsoft_graph_token.json"
            self.assertTrue(google.exists())
            self.assertTrue(microsoft.exists())
            self.assertEqual(json.loads(google.read_text(encoding="utf-8"))["provider"], "google")
            self.assertEqual(json.loads(microsoft.read_text(encoding="utf-8"))["provider"], "microsoft")

    def test_token_eater_attaches_google_secret_section(self):
        from scripts.token_eater import eat_pasted_text

        with tempfile.TemporaryDirectory(prefix="token-eater-secret-") as tmp:
            text = """Google -->
ya29.fake-google-token

Google secret -->
client-secret-value
"""
            result = eat_pasted_text(workspace=tmp, pasted_text=text)
            self.assertEqual(result["status"], "success")
            google = Path(tmp) / ".secrets" / "google_workspace_token.json"
            data = json.loads(google.read_text(encoding="utf-8"))
            self.assertEqual(data["provider"], "google")
            self.assertEqual(data["client_secret"], "client-secret-value")

    def test_token_eater_recognizes_pasted_google_client_credentials(self):
        from scripts.token_eater import eat_pasted_text

        with tempfile.TemporaryDirectory(prefix="token-eater-google-client-") as tmp:
            text = """Google -->
1234567890-example.apps.googleusercontent.com

Google secret -->
client-secret-value
"""
            result = eat_pasted_text(workspace=tmp, pasted_text=text)
            self.assertEqual(result["status"], "success")
            google = Path(tmp) / ".secrets" / "google_workspace_token.json"
            data = json.loads(google.read_text(encoding="utf-8"))
            self.assertEqual(data["provider"], "google")
            self.assertEqual(data["client_id"], "1234567890-example.apps.googleusercontent.com")
            self.assertEqual(data["client_secret"], "client-secret-value")
            self.assertEqual(data["access_token"], "")

    def test_token_eater_recognizes_pasted_microsoft_client_id(self):
        from scripts.token_eater import eat_pasted_text

        with tempfile.TemporaryDirectory(prefix="token-eater-ms-client-") as tmp:
            text = """Microsoft -->
11111111-2222-3333-4444-555555555555
"""
            result = eat_pasted_text(workspace=tmp, pasted_text=text)
            self.assertEqual(result["status"], "success")
            microsoft = Path(tmp) / ".secrets" / "microsoft_graph_token.json"
            data = json.loads(microsoft.read_text(encoding="utf-8"))
            self.assertEqual(data["provider"], "microsoft")
            self.assertEqual(data["client_id"], "11111111-2222-3333-4444-555555555555")
            self.assertEqual(data["access_token"], "")

    def test_oauth_wizard_reads_parked_client_ids(self):
        from scripts.oauth_token_wizard import google_client_config, microsoft_client_config

        with tempfile.TemporaryDirectory(prefix="oauth-wizard-client-") as tmp:
            root = Path(tmp)
            secrets = root / ".secrets"
            secrets.mkdir()
            (secrets / "google_workspace_token.json").write_text(
                json.dumps({"access_token": "1234567890-example.apps.googleusercontent.com", "client_secret": "secret"}),
                encoding="utf-8",
            )
            (secrets / "microsoft_graph_token.json").write_text(
                json.dumps({"access_token": "11111111-2222-3333-4444-555555555555"}),
                encoding="utf-8",
            )
            self.assertEqual(google_client_config(root)["client_id"], "1234567890-example.apps.googleusercontent.com")
            self.assertEqual(google_client_config(root)["client_secret"], "secret")
            self.assertEqual(microsoft_client_config(root)["client_id"], "11111111-2222-3333-4444-555555555555")

    def test_oauth_wizard_normalizes_token_metadata(self):
        from scripts.oauth_token_wizard import _normalize_oauth_token

        token = _normalize_oauth_token(
            {"access_token": "not-printed", "expires_in": 3600, "scope": "User.Read Files.Read"},
            provider="microsoft",
            client_id="11111111-2222-3333-4444-555555555555",
            tenant_id="common",
        )
        self.assertEqual(token["provider"], "microsoft")
        self.assertEqual(token["scopes"], ["User.Read", "Files.Read"])
        self.assertTrue(token["expires_at"])
        self.assertEqual(token["tenant_id"], "common")

    def test_oauth_wizard_has_safer_default_google_scope_profile(self):
        from scripts.oauth_token_wizard import GOOGLE_SCOPE_PROFILES

        self.assertIn("https://www.googleapis.com/auth/drive.metadata.readonly", GOOGLE_SCOPE_PROFILES["workspace"])
        self.assertIn("https://www.googleapis.com/auth/calendar.readonly", GOOGLE_SCOPE_PROFILES["workspace"])
        self.assertNotIn("https://www.googleapis.com/auth/gmail.readonly", GOOGLE_SCOPE_PROFILES["workspace"])
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", GOOGLE_SCOPE_PROFILES["full"])


if __name__ == "__main__":
    unittest.main()

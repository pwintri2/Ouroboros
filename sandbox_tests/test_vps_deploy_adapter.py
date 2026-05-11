import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.vps_deploy_adapter import (
    DEFAULT_RSYNC_EXCLUDES,
    REMOTE_ROOT,
    VPSDeployAdapter,
    VPSProfile,
    normalize_remote_target,
    redact_command,
    redact_sensitive_text,
)


class TestVPSDeployAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vps-deploy-adapter-")
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, "index.html").write_text("ok", encoding="utf-8")
        self.profile = VPSProfile(profile_id="test", ssh_host_alias="wintrip-vps", user="deploy", port=2222)

    def test_remote_target_allowlist_accepts_root_and_children_only(self):
        self.assertEqual(normalize_remote_target(""), REMOTE_ROOT)
        self.assertEqual(normalize_remote_target("assets"), REMOTE_ROOT + "assets/")
        self.assertEqual(normalize_remote_target(REMOTE_ROOT + "assets/css"), REMOTE_ROOT + "assets/css/")

        bad_paths = [
            "/var/www/philip-wintrip.nl/html/",
            "../html/Ouroboros",
            "assets/../.secrets",
            "$HOME/Ouroboros",
            "assets;rm -rf /",
            "assets with spaces",
            "~/Ouroboros",
        ]
        for path in bad_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    normalize_remote_target(path)

    def test_sync_preview_builds_dry_run_rsync_with_fixed_target_and_excludes(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="dry run ok token=SECRET", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.sync_preview(source_path=".", remote_path="assets", prefer_bridge=False)

        self.assertEqual(result["status"], "preview")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["mutated"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["remote_target"], REMOTE_ROOT + "assets/")
        cmd = calls[0]
        self.assertIn("--dry-run", cmd)
        self.assertIn("--exclude", cmd)
        self.assertIn(".secrets/", cmd)
        self.assertIn(".env*", cmd)
        self.assertIn("**/*.gguf", cmd)
        self.assertIn("--safe-links", cmd)
        self.assertIn("--protect-args", cmd)
        self.assertNotIn("SECRET", result["stdout"])
        self.assertEqual(set(DEFAULT_RSYNC_EXCLUDES).issuperset({".git/", ".secrets/", ".env*", "wintrip_brain/", "data/uploads/"}), True)

    def test_sync_execute_blocks_without_exact_akkoord_before_rsync(self):
        calls = []
        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=lambda cmd, **kwargs: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        )

        result = adapter.sync_execute(approval="akkoord", prefer_bridge=False)

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["mutated"])
        self.assertEqual(calls, [])

    def test_sync_execute_runs_without_dry_run_only_after_akkoord(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="sent index.html", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.sync_execute(approval="Akkoord", prefer_bridge=False)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["executed"])
        self.assertTrue(result["mutated"])
        self.assertNotIn("--dry-run", calls[0])
        self.assertEqual(result["remote_target"], REMOTE_ROOT)

    def test_login_check_uses_batch_mode_and_redacts_output(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="ok password=SECRET", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.login_check(prefer_bridge=False)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["login_ok"])
        self.assertIn("BatchMode=yes", calls[0])
        self.assertIn("PasswordAuthentication=no", calls[0])
        self.assertNotIn("SECRET", result["stdout"])

    def test_redaction_covers_tokens_and_command_identity_files(self):
        self.assertNotIn("SECRET", redact_sensitive_text("api_key=SECRET token=SECRET password=SECRET"))
        command = redact_command(["ssh", "-o", "IdentityFile /home/user/.ssh/id_rsa", "deploy@host"])
        self.assertNotIn("id_rsa", command)

    def test_status_unconfigured_never_fakes_success_or_credentials(self):
        adapter = VPSDeployAdapter(profile=VPSProfile(ssh_host_alias=""), workspace=self.tmp.name)
        result = adapter.status(prefer_bridge=False)
        self.assertEqual(result["status"], "unconfigured")
        self.assertFalse(result["fake_success"])
        self.assertFalse(result["profile"]["credentials_returned"])
        self.assertEqual(result["remote_target"], REMOTE_ROOT)


if __name__ == "__main__":
    unittest.main()

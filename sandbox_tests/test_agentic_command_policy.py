"""Shell command policy verdict tests."""

import unittest

from controller import agentic_command_policy as policy


class CommandPolicyTests(unittest.TestCase):
    def test_empty_command_is_denied(self):
        verdict = policy.evaluate_command("")
        self.assertEqual(verdict["verdict"], policy.VERDICT_DENY)

    def test_default_allowed_command_passes(self):
        verdict = policy.evaluate_command("git status -s")
        self.assertEqual(verdict["verdict"], policy.VERDICT_ALLOW)
        self.assertEqual(verdict["matched_rule"], "git status*")

    def test_unknown_command_requires_approval(self):
        verdict = policy.evaluate_command("custom-tool --flag")
        self.assertEqual(verdict["verdict"], policy.VERDICT_REQUIRES_APPROVAL)
        self.assertTrue(verdict["approval_phrase_required"])

    def test_dangerous_pattern_is_denied(self):
        verdict = policy.evaluate_command("rm -rf /")
        self.assertEqual(verdict["verdict"], policy.VERDICT_DENY)
        self.assertTrue(verdict["matched_rule"])

    def test_pipe_and_redirect_escalate(self):
        verdict = policy.evaluate_command("ls -la > /tmp/out.txt")
        self.assertEqual(verdict["verdict"], policy.VERDICT_REQUIRES_APPROVAL)

    def test_segment_chain_uses_strictest_verdict(self):
        verdict = policy.evaluate_command("ls && rm -rf /")
        self.assertEqual(verdict["verdict"], policy.VERDICT_DENY)

    def test_newline_command_is_denied(self):
        verdict = policy.evaluate_command("ls\nrm -rf /")
        self.assertEqual(verdict["verdict"], policy.VERDICT_DENY)

    def test_multi_segment_with_unknown_segment_requires_approval(self):
        verdict = policy.evaluate_command("ls && custom-tool")
        self.assertEqual(verdict["verdict"], policy.VERDICT_REQUIRES_APPROVAL)

    def test_explain_verdict_contains_reason(self):
        verdict = policy.evaluate_command("git status")
        text = policy.explain_verdict(verdict)
        self.assertIn("Allow", text)

    def test_merge_user_rules_keeps_defaults(self):
        allow, deny = policy.merge_user_rules(allow_patterns=["yarn build*"], deny_patterns=["forbidden*"])
        self.assertIn("git status*", allow)
        self.assertIn("yarn build*", allow)
        self.assertIn("forbidden*", deny)
        self.assertIn("rm -rf /*", deny)


if __name__ == "__main__":
    unittest.main()

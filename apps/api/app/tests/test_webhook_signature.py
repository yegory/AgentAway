import hashlib
import hmac
import unittest

from fastapi import HTTPException

from app.routes.webhooks import command_from_payload, verify_github_signature


class WebhookSignatureTests(unittest.TestCase):
    def test_valid_signature_is_accepted(self) -> None:
        body = b'{"ok":true}'
        secret = "dev-webhook-secret"
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        verify_github_signature(body, f"sha256={digest}", secret)

    def test_invalid_signature_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            verify_github_signature(b"{}", "sha256=bad", "dev-webhook-secret")

        self.assertEqual(raised.exception.status_code, 401)

    def test_deleted_issue_comment_does_not_create_command(self) -> None:
        payload = {"action": "deleted", "comment": {"body": "/agent plan"}}

        self.assertIsNone(command_from_payload("issue_comment", payload))

    def test_created_issue_comment_can_create_command(self) -> None:
        payload = {"action": "created", "comment": {"body": "/agent plan"}}

        parsed = command_from_payload("issue_comment", payload)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "plan")

    def test_created_issue_comment_can_create_proceed_command(self) -> None:
        payload = {"action": "created", "comment": {"body": "/agent proceed"}}

        parsed = command_from_payload("issue_comment", payload)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "proceed")

    def test_created_issue_comment_can_create_short_fixplan_command(self) -> None:
        payload = {"action": "created", "comment": {"body": "/fixplan keep the plan smaller"}}

        parsed = command_from_payload("issue_comment", payload)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "fixplan")

    def test_bot_issue_comment_does_not_create_command(self) -> None:
        payload = {
            "action": "created",
            "comment": {
                "body": "/fix add tests max 2 files",
                "user": {"login": "agentaway[bot]", "type": "Bot"},
            },
        }

        self.assertIsNone(command_from_payload("issue_comment", payload))


if __name__ == "__main__":
    unittest.main()

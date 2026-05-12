import unittest

from app.services.command_parser import parse_agent_command


class CommandParserTests(unittest.TestCase):
    def test_agent_plan_command_is_parsed(self) -> None:
        parsed = parse_agent_command("/agent plan")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "plan")
        self.assertEqual(parsed.raw_text, "/agent plan")
        self.assertIn(".github/workflows/**", parsed.modifiers["forbidden_paths"])

    def test_frontend_modifier_sets_allowed_paths(self) -> None:
        parsed = parse_agent_command("/agent fix but only touch frontend files and add tests")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "fix")
        self.assertTrue(parsed.modifiers["tests_required"])
        self.assertEqual(parsed.modifiers["allowed_paths"], ["apps/web/**"])

    def test_agent_proceed_command_is_parsed(self) -> None:
        parsed = parse_agent_command("/agent proceed")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "proceed")

    def test_agent_fixplan_command_is_parsed(self) -> None:
        parsed = parse_agent_command("/agent fixplan keep it to one file")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "fixplan")

    def test_short_command_alias_is_parsed(self) -> None:
        parsed = parse_agent_command("/proceed")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.command, "proceed")

    def test_unknown_short_command_is_ignored(self) -> None:
        self.assertIsNone(parse_agent_command("/approve"))

    def test_agent_numeric_reply_is_not_treated_as_plan(self) -> None:
        self.assertIsNone(parse_agent_command("/agent 1 1 3"))

    def test_non_agent_comment_is_ignored(self) -> None:
        self.assertIsNone(parse_agent_command("Could someone look at this?"))


if __name__ == "__main__":
    unittest.main()

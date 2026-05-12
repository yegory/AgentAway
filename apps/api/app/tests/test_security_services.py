import unittest

from app.services.auth import auth_is_optional_for_dev
from app.services.crypto import decrypt_secret, encrypt_secret, key_hint
from app.services.policy_engine import path_is_forbidden, validate_file_plan
from app.services.providers import normalize_provider, provider_defaults


class SecurityServiceTests(unittest.TestCase):
    def test_secret_encryption_roundtrip(self) -> None:
        encrypted = encrypt_secret("sk-test-secret")

        self.assertNotIn("sk-test-secret", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "sk-test-secret")

    def test_key_hint_masks_secret(self) -> None:
        self.assertEqual(key_hint("sk-123456"), "****3456")

    def test_policy_rejects_forbidden_paths(self) -> None:
        self.assertTrue(path_is_forbidden(".env"))
        self.assertTrue(path_is_forbidden("../outside.py"))
        self.assertFalse(path_is_forbidden("src/greeting.py"))

    def test_policy_enforces_max_files(self) -> None:
        result = validate_file_plan(["a.py", "b.py"], max_files=1)

        self.assertFalse(result.allowed)

    def test_provider_defaults_are_available(self) -> None:
        self.assertEqual(normalize_provider("DeepSeek"), "deepseek")
        self.assertTrue(provider_defaults("deepseek").model_name)

    def test_auth_is_optional_in_unconfigured_dev(self) -> None:
        self.assertTrue(auth_is_optional_for_dev())


if __name__ == "__main__":
    unittest.main()

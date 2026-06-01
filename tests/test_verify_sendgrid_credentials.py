import unittest
from unittest.mock import patch

from scripts.verify_sendgrid_credentials import (
    VerificationConfig,
    build_payload,
    build_request,
    classify_response,
    main,
)


class SendGridVerifierTests(unittest.TestCase):
    def test_build_payload_enables_sandbox_by_default(self):
        config = VerificationConfig(
            api_key="SG.test",
            from_email="support@example.com",
            to_email="ops@example.com",
        )

        payload = build_payload(config)

        self.assertEqual(payload["from"]["email"], "support@example.com")
        self.assertEqual(payload["personalizations"][0]["to"][0]["email"], "ops@example.com")
        self.assertTrue(payload["mail_settings"]["sandbox_mode"]["enable"])

    def test_build_payload_can_disable_sandbox_for_real_delivery(self):
        config = VerificationConfig(
            api_key="SG.test",
            from_email="support@example.com",
            to_email="ops@example.com",
            sandbox=False,
        )

        payload = build_payload(config)

        self.assertNotIn("mail_settings", payload)

    def test_build_request_sets_sendgrid_auth_headers(self):
        config = VerificationConfig(
            api_key="SG.test",
            from_email="support@example.com",
            to_email="ops@example.com",
        )

        request = build_request(config)

        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer SG.test")
        self.assertEqual(request.get_header("Content-type"), "application/json")

    def test_classify_response_accepts_sendgrid_success_statuses(self):
        for status in (200, 202):
            with self.subTest(status=status):
                ok, message = classify_response(status, "", sandbox=True)

                self.assertTrue(ok)
                self.assertIn(str(status), message)

    def test_classify_response_flags_unauthorized_key(self):
        ok, message = classify_response(401, '{"errors":[]}', sandbox=True)

        self.assertFalse(ok)
        self.assertIn("Rotate SENDGRID_API_KEY", message)

    def test_main_requires_api_key_from_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            exit_code = main(["--from-email", "support@example.com", "--to-email", "ops@example.com"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()

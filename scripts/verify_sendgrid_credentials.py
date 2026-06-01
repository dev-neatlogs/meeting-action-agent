#!/usr/bin/env python3
"""Verify that the configured SendGrid API key can call the Mail Send API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_ENDPOINT = "https://api.sendgrid.com/v3/mail/send"
DEFAULT_SUBJECT = "SendGrid credential verification"
SUCCESS_STATUSES = {200, 202}


@dataclass(frozen=True)
class VerificationConfig:
    api_key: str
    from_email: str
    to_email: str
    subject: str = DEFAULT_SUBJECT
    sandbox: bool = True
    endpoint: str = DEFAULT_ENDPOINT
    timeout: float = 10.0


def build_payload(config: VerificationConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "personalizations": [{"to": [{"email": config.to_email}]}],
        "from": {"email": config.from_email},
        "subject": config.subject,
        "content": [
            {
                "type": "text/plain",
                "value": (
                    "This is a SendGrid credential verification request for "
                    "the support-copilot email workflow."
                ),
            }
        ],
    }

    if config.sandbox:
        payload["mail_settings"] = {"sandbox_mode": {"enable": True}}

    return payload


def build_request(config: VerificationConfig) -> urllib.request.Request:
    return urllib.request.Request(
        config.endpoint,
        data=json.dumps(build_payload(config)).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def send_verification(config: VerificationConfig) -> tuple[int, str]:
    request = build_request(config)
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def classify_response(status: int, body: str, sandbox: bool) -> tuple[bool, str]:
    if status in SUCCESS_STATUSES:
        expected = "202 Accepted" if not sandbox else "200 OK or 202 Accepted"
        return True, f"SendGrid accepted the Mail Send request ({status}; expected {expected})."

    if status == 401:
        return (
            False,
            "SendGrid returned 401 Unauthorized. Rotate SENDGRID_API_KEY and verify "
            "the production environment is loading the new secret.",
        )

    if status == 403:
        return (
            False,
            "SendGrid returned 403 Forbidden. Confirm the key has Mail Send permission "
            "and that the account is not blocked by billing, sender, or security policy.",
        )

    details = f" Response body: {body.strip()}" if body.strip() else ""
    return False, f"SendGrid returned unexpected status {status}.{details}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a SendGrid API key by calling the Mail Send endpoint. Sandbox "
            "mode is enabled by default so no email is delivered."
        )
    )
    parser.add_argument(
        "--api-key-env",
        default="SENDGRID_API_KEY",
        help="Environment variable containing the SendGrid API key.",
    )
    parser.add_argument("--from-email", required=True, help="Verified sender email address.")
    parser.add_argument("--to-email", required=True, help="Recipient address for the test request.")
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="Subject for the test request.")
    parser.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Deliver a real test email. A healthy production key should return 202 Accepted.",
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        print(f"Missing {args.api_key_env}; export it before running verification.", file=sys.stderr)
        return 1

    config = VerificationConfig(
        api_key=api_key,
        from_email=args.from_email,
        to_email=args.to_email,
        subject=args.subject,
        sandbox=not args.no_sandbox,
        endpoint=args.endpoint,
        timeout=args.timeout,
    )

    try:
        status, body = send_verification(config)
    except urllib.error.URLError as exc:
        print(f"Unable to reach SendGrid: {exc}", file=sys.stderr)
        return 3

    ok, message = classify_response(status, body, config.sandbox)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

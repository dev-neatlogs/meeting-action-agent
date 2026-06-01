import json
import os
import urllib.error
import urllib.request
from typing import List, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SendEmailToolInput(BaseModel):
    from_email: str = Field(description="Sender email address.")
    to_emails: List[str] = Field(description="Recipient email addresses.")
    subject: str = Field(description="Email subject line.")
    plain_text: str = Field(description="Plain-text email body.")
    html_content: Optional[str] = Field(
        default=None, description="Optional HTML email body."
    )


class SendEmailTool(BaseTool):
    """
    Sends an email using SendGrid v3 Mail Send.

    This tool is intentionally strict about 401 errors: if SendGrid returns
    401 Unauthorized, we return a non-ambiguous message telling operators to
    rotate/verify SENDGRID_API_KEY with "Mail Send" permission.
    """

    name: str = "Send Email"
    description: str = (
        "Send an email via SendGrid (v3 Mail Send). "
        "Input fields: from_email, to_emails, subject, plain_text, html_content(optional). "
        "Returns the HTTP status (and limited response details) for observability."
    )
    args_schema: Type[BaseModel] = SendEmailToolInput

    def _send_sendgrid_mail(self, payload: dict) -> tuple[int, str]:
        api_key = os.getenv("SENDGRID_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "Missing SENDGRID_API_KEY. Set it in the environment with "
                '"Mail Send" permission, then restart the service.'
            )

        url = "https://api.sendgrid.com/v3/mail/send"
        data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                status = int(getattr(resp, "status", 200))
                body_bytes = resp.read() or b""
                body = body_bytes.decode("utf-8", errors="replace")
                return status, body
        except urllib.error.HTTPError as e:
            # HTTPError is also raised for non-2xx responses.
            status = int(e.code)
            body_bytes = e.read() or b""
            body = body_bytes.decode("utf-8", errors="replace")
            return status, body

    def _run(
        self,
        from_email: str,
        to_emails: List[str],
        subject: str,
        plain_text: str,
        html_content: Optional[str] = None,
    ) -> str:
        to_list = [{"email": e} for e in to_emails]
        personalization = [{"to": to_list}]

        content_blocks = [{"type": "text/plain", "value": plain_text}]
        if html_content:
            content_blocks.append({"type": "text/html", "value": html_content})

        payload = {
            "personalizations": personalization,
            "from": {"email": from_email},
            "subject": subject,
            "content": content_blocks,
        }

        status, body = self._send_sendgrid_mail(payload)

        # Observability: keep messages deterministic and avoid leaking secrets.
        if status == 202:
            # SendGrid typically returns 202 with an empty body.
            return f"SendGrid mail accepted: 202 Accepted (response_body_len={len(body)})"
        if status == 401:
            # Explicitly match the triage pattern and recommend credential rotation.
            return (
                "SendGrid 401 Unauthorized. Verify/rotate SENDGRID_API_KEY "
                'in production with "Mail Send" permissions, then restart the service.'
            )
        if status >= 400:
            snippet = body[:500] if body else ""
            return f"SendGrid error: HTTP {status}. response_body_snippet={snippet}"

        return f"SendGrid unexpected status: HTTP {status}. response_body_len={len(body)}"


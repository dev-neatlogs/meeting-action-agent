# SendGrid credential rotation runbook

Tracking URL: http://localhost:3002/triage/a756f71a-6446-449d-92c4-d8a07c004c54

Use this runbook when the support-copilot `Send Email` tool reports
`EmailDeliveryError: SendGrid 401` or when the `Send Email` span no longer
returns a healthy Mail Send response.

## 1. Verify current production configuration

1. Confirm which secret manager or environment variable source populates
   `SENDGRID_API_KEY` for production.
2. Confirm the running agent service has the expected secret version loaded.
3. Check the SendGrid dashboard for:
   - revoked or expired API keys
   - account security holds
   - billing or sender-verification blocks
   - IP allowlist changes, if the account uses IP Access Management

Do not print or paste the API key into logs, chat, issue comments, or shell
history. Load it through the existing secret-management path whenever possible.

## 2. Rotate the key

1. In SendGrid, create a new API key with **Mail Send** permission only.
2. Update the production `SENDGRID_API_KEY` secret to the new value.
3. Restart or redeploy the support-copilot agent service so it reads the updated
   secret.
4. Keep the previous key available for rollback until verification passes, then
   revoke it.

## 3. Verify Mail Send access

From a secure operator shell with the new key loaded:

```bash
export SENDGRID_API_KEY="..."
python scripts/verify_sendgrid_credentials.py \
  --from-email support@example.com \
  --to-email ops@example.com
```

The verifier uses SendGrid sandbox mode by default. It validates that the key can
authenticate and call the Mail Send endpoint without delivering an email. A
healthy sandbox request returns `200 OK` or `202 Accepted`.

To verify real delivery after the service restart, run:

```bash
python scripts/verify_sendgrid_credentials.py \
  --from-email support@example.com \
  --to-email ops@example.com \
  --no-sandbox
```

A healthy non-sandbox Mail Send request should return `202 Accepted`.

## 4. Verify the workflow and observability

1. Execute a test ticket through the `crewai-support-bot` workflow.
2. Confirm the `Send Email` tool span returns `202 Accepted`.
3. In Neatlogs, inspect the linked triage and recent sibling traces:
   - `triage_get(a756f71a-6446-449d-92c4-d8a07c004c54)`
   - `get_trace_context(<new_test_trace_id>)`
   - `search_traces("SendGrid 401", mode="keyword")`
4. Mark the triage `resolved` only after the production workflow is verified and
   the failure pattern is no longer present. If this PR is merged before
   production verification, mark it `in_progress`.

## Rollback

If the new key fails:

1. Restore the previous `SENDGRID_API_KEY` secret version.
2. Restart or redeploy the agent service.
3. Re-run the verifier and a workflow test.
4. If both keys fail, investigate sender verification, billing status, security
   holds, or IP allowlisting before generating additional keys.

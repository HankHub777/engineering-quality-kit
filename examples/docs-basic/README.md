# Operations runbook

## Restart the service

1. Confirm no deploy is running.
2. Run the restart command.
3. Check the health endpoint returns `200`.

## Roll back

If the health check fails, redeploy the previous release.

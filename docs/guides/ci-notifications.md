# CI and release notifications

The reviewable sources are `scripts/slack_sink.py` and
`scripts/himalaia_nightly_alert.py`. They are adapted from the operational
helpers; this change does not install them or mutate running services.
Configure `ORCHESTRA_DIR` explicitly when promoting these sources. The standalone
sink imports the operational `slack_api` adapter; no credentials are bundled.

`release` and `deploy` route to `release`. The channel comes from `release` in
the existing channel map or the `RELEASE_CHANNEL_ID` environment override.
There is no built-in channel ID. Without it, delivery falls back to `orchestra`,
with both a log warning and a visible message explaining the fallback.

The nightly helper sends one failure attachment per run, marking the run only
after successful delivery. Success clears the open marker without sending a
resolved message. Cancellation without a failure does not send or clear an
incident. `--dry-run` does not change state.

Set `ALERT_SENDER_HOST` and `ALERT_SENDER_PATH` to preserve the remote Alerts-app
relay; otherwise the existing Orchestra Slack adapter is used. The destination
remains `alert`. No host or secret is inferred from this repository.

Only one nightly sender should own delivery. The default
`HIMALAIA_NIGHTLY_ALERT_OWNER=relay` retains the homelab sender. When adopting the
Himalaia workflow sender, first provision its Slack configuration, set the
service environment owner to `workflow`, and then set the identically named
Forgejo repository variable to `workflow`. This prevents duplicate alerts;
coordinate that short handover and verify delivery in a separately authorized
rollout. This task neither changes service configuration nor sends a message.

The generic sink has no CI outcome field; its generic `ci` route is preserved.
Failure/success filtering belongs to the outcome-aware CI producers, not a
heuristic over notification prose. The callers must use `alert` for CI failures.

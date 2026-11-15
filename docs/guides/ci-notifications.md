# CI and release notifications

The canonical installable sources are `bin/slack_sink.py` and
`bin/himalaia_nightly_alert.py`; `scripts/` contains compatibility symlinks to
those files. Promote the `bin/` files together, not the symlinks alone. The sink
imports the existing operational `slack_api` adapter; no credentials are bundled.
The runtime root defaults to the parent of the resolved `bin/` directory, with
an explicit `ORCHESTRA_DIR` override. It never depends on the working directory.

`release` and `deploy` route to `release`. The approved default channel is
`C0CAEALG03V`. The existing channel-map `release` entry overrides the default;
`RELEASE_CHANNEL_ID` overrides both when nonempty. An explicitly empty map entry
falls back to `orchestra`, with a visible message and log warning. Slack errors
`not_in_channel`, `is_archived` and `channel_not_found` trigger one additional
post to `orchestra`, with the reason and a visible fallback note. Authentication
and other failures do not reroute; a failed fallback is logged and returns false.

The nightly helper sends one failure attachment per run, marking the run only
after successful delivery. Success clears the open marker without sending a
resolved message. Cancellation without a failure does not send or clear an
incident. `--dry-run` does not change state.

## Service promotion

`deploy/systemd/orchestra-himalaia-nightly-alert.service.in` is the source for
the user service. Render every placeholder before installing it:

- `ORCHESTRA_DIR`: absolute operational root containing `bin`, `scratch`, `logs`.
- `CLI_PATH`: absolute directory containing the authenticated `fj` CLI.
- `ALERT_SENDER_HOST` and `ALERT_SENDER_PATH`: preserve the existing SSH Alerts
  relay settings; obtain them from the current service/helper, never a secret.

The unit explicitly sets the runtime root and relay settings, even when systemd
starts from another directory. Keep the existing timer. Promote the two canonical
files and rendered unit together, then reload the user systemd manager. This
source PR does not install files, reload services, or send real notifications.
The regression test launches the `bin/` entrypoint outside the runtime root,
with and without the rendered unit environment, using only fake `fj`, SSH and
Slack adapters; it verifies successful state persistence.

Only one nightly sender should own delivery. The default
`HIMALAIA_NIGHTLY_ALERT_OWNER=relay` retains the homelab sender. When adopting the
Himalaia workflow sender, first provision its Slack configuration, set the
service environment owner to `workflow`, and then set the identically named
Forgejo repository variable to `workflow`. Coordinate this handover separately
and verify delivery before retiring the relay. This PR keeps relay ownership.

The generic sink has no CI outcome field; its generic `ci` route is preserved.
Failure/success filtering belongs to outcome-aware producers. Callers must use
`alert` for CI failures.

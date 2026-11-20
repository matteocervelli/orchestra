# Changelog

All notable changes to Orchestra are documented here.

## [Unreleased]

### Added

- Seed the reusable Orchestra workflow repository with dual-forge flow,
  Forgejo-only CI, reviewable launcher and Slack/ledger sources, documentation,
  tests, and synthetic boundary fixtures.

### Changed

- Reconcile the initial promotion changelog with the included implementation
  commits and current Nexus dependency status.

### Fixed

- Escape Slack control sequences in release text and fail visibly when nightly
  CI queries fail, preserving the existing alert state.
- Canonical `bin/` Slack sink routes releases to the approved default channel
  (with environment/config overrides), retries unavailable release channels once
  on Orchestra, and clears nightly recovery silently. Nightly resolves its runtime
  root outside the working directory; a service template preserves relay settings.

- Avoid duplicate nonterminal Forgejo CI runs in the reusable pipeline.
- Enforce the ignored tracked-file policy across every tracked path, including
  force-added credential-like filenames.

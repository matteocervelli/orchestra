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

- Avoid duplicate nonterminal Forgejo CI runs in the reusable pipeline.
- Enforce the ignored tracked-file policy across every tracked path, including
  force-added credential-like filenames.

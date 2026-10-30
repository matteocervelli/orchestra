# Changelog

All notable changes to Orchestra are documented here.

## [Unreleased]

### Fixed

- SOURCE author-derived titles reject recognizable token, opaque-run and email
  shapes before display. Curated titles retain precedence; this bounded filter
  does not provide general PII anonymization.
- Inactive SOURCE dashboard export pairs alias-merged needs with its author's
  intent marker, clearing stale metadata when an unmarked alias wins. Its narrow
  dedupe adapter remains a runtime-unaccepted candidate, separate from identity.

- Inactive SOURCE dashboard distinguishes exact-text author information from
  human requests and infers mockup approval from an explicit approval question;
  later questions, independent gates and recorded answers remain authoritative.
- SOURCE presentation reuses specific Italian task subjects without changing
  task identity inputs; failed technical work no longer creates a placeholder
  human question while explicit decisions and curated text remain authoritative.
- Inactive SOURCE ownership candidate preserves explicit source assignments and
  separates display projects from cited dependencies, mathematical terms and
  exclusions. Unidentified projects no longer default to Orchestra in that candidate.

### Added

- Inert legacy dashboard repository-alias companion with pinned Native helper
  generation, exact donor hashes and a standalone JavaScript behavior gate.
- Dedicated repository baseline with dual-forge flow and Forgejo-only CI.
- Reviewable launcher, Slack client, thread routing, and ledger reconciliation
  source extracted from the operational Orchestra directory.
- Runtime-state exclusion policy, guard tests, and synthetic boundary fixtures.

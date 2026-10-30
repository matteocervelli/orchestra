# Test map

- `test_repository_boundary.py`: ignore and tracked-content guard.
- `test_ledger_sync.py`: completion reconciliation and idempotency.
- `test_slack_api.py`: request encoding and injected token behavior without
  network or credential access.
- `test_slack_thread.py`: route/thread selection with synthetic files.
- `test_launchers.py`: launcher argument boundaries and one-cycle autospawn
  behavior with fake commands.
- `test_synthetic_evals.py`: schema and expected result checks for synthetic
  boundary cases.

Dashboard regression files (`test_dashboard_*.py`) use invented tmp_path data:
- titles/sources/text: shared admission, curated title precedence, meaningful
  parentheses, transactional note preservation, deterministic lock contention
  and atomic-write failure; edited_fields projection and explicit blank fallback;
- provenance/identity: bounded metadata, exact-mandate receipts, owner/forge
  separation, stable opaque IDs, independent asks and exact-ID synthetic lookup;
- quality: local artifact versus integration, bound detail parity and stale or
  missing snapshot evidence;
- runtime export: immutable donor hashes, canonical byte equality, thin adapter
  imports, explicit CLI inputs and separate non-ready identity candidates.
These tests do not claim runtime activation, real API link resolution, semantic
truth of reports or provider/network verification.

Source quality CI also runs Vulture at confidence 80 and Radon with closures,
rejecting any grade above B. Unit coverage includes public text/choice contracts,
reference authority, bound child-detail evidence and the explicit-path quality
module CLI; the shared Python 3.12 branch-aware coverage threshold remains 80%.


`test_dashboard_history.py` covers explicit historical source→opaque ownership,
missing raw targets, atomic conflicts/collisions, new raw task IDs, independent
child cards, protected fields and qualified PR objects for both forges. It uses
invented fixtures only. A separate external frozen Nexus slice exercises real
Assembly inputs and exact-ID consumer lookup without executing full build/log
readers; it is not committed as runtime data or claimed as full activation proof.

`test_dashboard_repository_projection.py` exercises the pinned SOURCE publisher/main bodies emitted by the real exporter with synthetic data and injected writer boundaries: YourCall12, C1 aliases/negative values, live/archive/detail coherence, digest, nested references and raw audit1. Extraction origin and Python3.12 AST pins are in producer provenance. Runtime export tests require an independent explicit21 inventory and verify one merged compatibility bundle, common/helper/before-vector guards, failure before output and unchanged donor bytes. These do not certify loaded consumer old URLs or real producer builds.

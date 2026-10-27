# Architecture map

The repository is an inert workflow-source package. Python modules contain
portable helpers; shell scripts preserve the legacy launcher behavior for
review and tests. No service starts from package import or repository checkout.

External ownership remains unchanged: Atrium stores durable application state,
Nexus owns orchestration and dispatch, GitHub owns backlog, and Forgejo owns CI.
The operational Orchestra directory is an external runtime consumer and is not
modified or read by tests.

The dashboard package has no root discovery, network client or generator. Runtime
consumption uses byte-identical package exports and thin adapters. Notes admission
changes one missing title under the shared lock; provenance is classification,
not approval authority. Detail enrichment needs exact item, unique microsecond
generation and compact-board digest binding. Default core bundles exclude identity
and collapse adapters. A separately reviewed candidate preserves opaque curated
IDs because the observed Atrium consumer performs exact-ID lookup.

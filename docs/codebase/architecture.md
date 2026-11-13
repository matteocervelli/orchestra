# Architecture map

The repository is an inert workflow-source package. Python modules contain
portable helpers; shell scripts preserve the legacy launcher behavior for
review and tests. No service starts from package import or repository checkout.

External ownership remains unchanged: Atrium stores durable application state,
Nexus owns orchestration and dispatch, GitHub owns backlog, and Forgejo owns CI.
The operational Orchestra directory is an external runtime consumer and is not
modified or read by tests.

# Delivery dependencies

Issue `matteocervelli/nexus#184` is P1 and depends on two P0 proofs:

| Dependency | Status at 2026-10-21 | Handling |
| --- | --- | --- |
| `matteocervelli/atrium#297` | Closed; implemented by Atrium PR #299, promoted by #302, deployed in 0.5.0 | Satisfied. |
| `matteocervelli/nexus#64` | Open; Nexus PR #191 merged to `auto/integration` | The repository and CI can be reviewed and promoted, but no extracted launcher is installed, activated, or connected to runtime. Activation remains gated on P0 closure. |

This repository task introduces no deployment workflow and performs no live
cutover. The operational directory continues running unchanged.

# Sources and licensing boundaries

This repository's original instructions, Python utilities and tests use the MIT
license in LICENSE. That license does not cover Amazon software or upstream
exploit material that is not distributed here.

The temporary-root procedure is based on the published kara adaptation of
[Delitants/GhostLock](https://github.com/Delitants/GhostLock/tree/5a9e2b08d0dca369df442c612a2693d3e7a771c6/kara),
which credits R0rt1z2/GhostLock and public Linux futex-PI research. Its
[provenance notice](https://github.com/Delitants/GhostLock/blob/5a9e2b08d0dca369df442c612a2693d3e7a771c6/kara/PROVENANCE.md)
states that the upstream fork-point commit has no license file and does not
grant a new license for that material. We do not vendor its source or binaries.
Downloading its referenced release is a separate operator action; review the
upstream terms. The helper patch utility changes only a pinned data parameter
in the operator's own local copy and verifies the result.

The [firetv-kara-standalone controller](https://github.com/Delitants/firetv-kara-standalone)
is an additional source for the exact-device workflow and restoration pattern.
Its MIT license belongs to its author. This project implements its own small
transport and configuration helpers rather than copying the controller.

[NikhilSiddhu/firetv-tvos](https://github.com/NikhilSiddhu/firetv-tvos) and
[jeremykenedy/fire-tv-ui](https://github.com/jeremykenedy/fire-tv-ui) were reviewed
for Home-routing techniques. Their launchers are not bundled or required.

Amazon Fire TV, Burton and related names identify the software being investigated.
Amazon APKs, framework libraries, firmware, signing keys and screenshots are not
included. Claude and Codex names describe compatible agent workflows, not an
endorsement by their providers.

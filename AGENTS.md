# Repository instructions

For Fire TV work, read `skills/firetv-burton/SKILL.md`, then the relevant reference.
The intended UI is the official Amazon Burton interface. A custom launcher does
not satisfy that request. Offline preparation and read-only inspection are the
only actions automated by `burton.py`; temporary root is a separate operator step.

All live state belongs in ignored `.local/` directories. Never add device
identifiers, network addresses, original configuration, screenshots, APKs, root
binaries, credentials or raw logs to Git. Synthetic test fixtures are acceptable.

Validation: `python3 -m unittest discover -s tests -v` and
`python3 tools/check_repository.py`. These never access a device. Do not test a
live exploit while maintaining this repository. Root retries require renewed
authorization; publishing a guide does not authorize modifying a connected TV.

Keep support claims limited to the verified matrix. New model/firmware support
requires separate evidence and review, not relaxed identity or hash checks.

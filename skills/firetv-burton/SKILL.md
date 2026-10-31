---
name: firetv-burton
description: Investigate and activate the official Amazon Burton Home UI on an owned Fire TV, verify compatibility, prepare configuration overrides, and restore the previous state. Use for the official redesigned Home, not third-party launchers or generic debloating.
---

# Official Fire TV Burton Home

Preserve the user's goal: activate the UI inside Amazon's original signed
launcher. Start with [compatibility and evidence](references/compatibility.md).
Only the AFTKA/kara build listed there has a tested live path. On other devices,
continue read-only investigation; do not reuse its root helper or relax gates.

Use the [operator workflow](references/workflow.md) for an eligible device and
the [recovery guide](references/recovery.md) for failure, rollback or unfreezing.
The flow is inspect → choose duration/protection → authorize root → obtain one
temporary session → backup → prepare offline → apply → verify → restore system
state → remove temporary access → reboot → verify again.

Non-obvious constraints:

- `launcher.isBurtonEnabled` and `launcherName` are outputs. Setting those public
  values alone does not activate Burton. The private Arcus eligibility and T1
  experiment override are the inputs used by this method.
- Read the user's existing authorization. Before a live kernel attempt, explain
  hang/reboot risk, temporary protection reduction, and the helper's OTA effects.
  Obtain informed authorization if it is not already established. Execute once;
  do not retry automatically, even when a preparation guard stops before the race.
- The launcher uses a device-type property and a serial. Read them from the
  selected device into private files; never borrow values from another device.
- Ask for duration/protection choices only when absent. Disclose the chosen
  expiry before applying it. Freezing refresh affects the whole Home config
  bundle; future firmware, launcher updates or reset-data can override it.
- Keep backups of the working configuration before mutation, compare hashes
  immediately before applying, preserve ownership/mode/SELinux labels, and retain
  a working root session until the launcher has been checked and recovery paths
  restored. A frozen process must be resumed or restarted on every error path.
- ADB reconstructs a remote shell command. Quote the complete daemon command as
  one argument; use `scripts/root_session.py` to preserve quoting and check the
  remote exit status. An upstream client exit code of zero does not prove that
  the command inside the daemon succeeded.
- Never freeze the entire preferences XML or make the database immutable. The
  database is opened for writing even on its read path; such a block can cause
  fallback to the old UI. Use the existing sync-date gate when requested.
- Restore the captured CEC/OTA states and all held OTA paths, then reboot. Root
  disappearing does not undo filesystem or settings changes. Keep the user's
  chosen Burton configuration while removing temporary access.

The helper preparation and config transformations in `scripts/burton.py` are
offline. `inspect` is read-only. Neither script starts an exploit, installs APKs,
flashes partitions, or grants itself permission. CI does not connect to TVs.
Resolve scripts relative to this skill's actual installation directory. Runbook
examples assume a repository clone; for an installed copy, set `BURTON_TOOLS` to
that copy's absolute `scripts/` path and keep the private case in a writable local
workspace, rather than writing device backups into the installed skill.

Report observed UI, reboot persistence, cleanup status and remaining limits.
Distinguish the tested manual procedure from newly packaged utilities: unit
tests validate their logic, not a new live hardware run. Never upload private
case folders when sharing results.

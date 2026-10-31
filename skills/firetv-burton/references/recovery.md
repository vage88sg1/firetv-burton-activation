# Recovery, rollback and unfreezing

Do not rerun live mode to repair a failed session. First distinguish an ordinary
command error, failed preparation, a parked post-race process, and a working root
daemon. Keep logs local. If the daemon works, preserve it until recovery is done.

## Probe or preparation failure before root

Read `before-system.json`. Restore `secure:block_cec_standby` to its captured
value with ordinary ADB; if the value was `null`, use `settings delete secure
block_cec_standby`, not `settings put ... null`. Check UID and SELinux. When the
log confirms a preparation stop before the vulnerable call, configuration and
kernel writes were not performed, but verify settings rather than assuming.

A post-race parked process must not be killed casually: dangling kernel state
may remain. Follow the upstream recovery guidance and reboot deliberately when
appropriate. A hung or inaccessible device may need an owner power cycle. A
reboot removes temporary root but does not restore moved files or settings.
If privileged filesystem restoration remains incomplete, report it explicitly;
another authorized access attempt may be needed after recovery.

## UID 0 exists, but commands appear denied

ADB joins remote arguments. The local form `adb shell helper --cmd 'a; b'` can
leave only `a` inside the daemon while `b` runs as the ordinary shell. Use the
provided RootSession transport: one quoted remote command and an inner status
marker. Do not conclude the root credentials are unusable from that quoting bug.

Android Binder calls from root's kernel SELinux context may fail to find services
even though the service is running. For package-manager restoration, the tested
controller pattern is `runcon u:r:shell:s0 /system/bin/pm ...` under the existing
UID 0 daemon. Do not change global SELinux policy or flash framework libraries.

## Restore helper side effects

Use `device_ops.py restore-paths` early and `restore-system`/`finish` at the end.
The original/held pairs are:

| Original | Held |
| --- | --- |
| `/data/ota_package` | `/data/local/tmp/kara-ota-package.PS7713-held` |
| `/cache/recovery/command` | `/cache/recovery/command.kara-PS7713-held` |
| `/cache/recovery/block.map` | `/cache/recovery/block.map.kara-PS7713-held` |

Restore a held path only when the original is absent. If both exist, inspect
their contents/metadata. An empty recreated directory can sometimes be removed
with `rmdir` after review; never recursively delete an OTA target to force a move.
Restore all three package enable states and both settings from the baseline,
including state 0 (default), rather than indiscriminately enabling everything.
Require verification. Reboot only after successful recovery, unless a hang makes
that impossible; then report what could not be restored.

## Immediate rollback of the UI/configuration

While the same root session is still working, keep the two original case files.
If apply fails during a write, the utility attempts to put them back automatically.
If the files were applied but the UI then fails, use a reviewed command file with
the provided root transport to:

1. Pause the current launcher process and check there is no active WAL/journal or
   preferences `.bak` needing recovery.
2. Stage `source.db` and `source.xml` under a private directory on the selected TV.
3. Write their contents back into the existing original DB/XML paths. Preserve
   ownership, mode and SELinux labels; verify hashes against `capture.json`.
4. Sync, restart the launcher, reopen Home, and confirm the previous working UI.
5. Restore OTA/CEC, clean up and reboot as in the normal finishing step.

Keep a finally/error path that resumes the paused process. Do not use `pm clear`,
a factory reset or uninstall-updates as the default rollback: they remove more
state than this configuration-only change.

## Later unfreeze or targeted rollback

After the final reboot there is no retained root session. A later change needs
new informed authorization for temporary privileged access; the skill does not
authorize repeated attempts on its own.

Capture **current** files in a new private case. For unfreezing, change only the
known bundle's `NextSyncTimeInMillis` long to 0 or restore its old captured value,
then restart Home. `burton.set_sync(raw_xml, 0)` is the offline transformation
available in scripts/burton.py; verify the semantic diff before applying it.
Amazon's next configuration may change Burton eligibility/treatment.

For reverting Burton itself, merge the original eligibility list and original
Burton experiment entry (or remove that entry if originally absent) into a copy
of the **current** configuration. Preserve other experiments, row metadata and
current preferences. Do not blindly restore an old whole preferences file after
the owner has made unrelated changes. Use an offline integrity check and the
same backup/hash/apply discipline; this merge is operator-assisted, not an
untested promise that a global rollback command can preserve every later change.

No file flag or sync date guarantees persistence against future Amazon firmware,
launcher replacement or app-data reset. Avoid making the database immutable:
its normal load path calls `getWritableDatabase` and starts a transaction, so a
write prohibition can prevent loading and bring back the built-in default UI.

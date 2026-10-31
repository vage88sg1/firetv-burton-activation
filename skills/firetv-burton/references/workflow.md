# Operator workflow: official Amazon Burton Home

This workflow uses an existing official launcher with dormant Burton code. It
does not install a replacement Home. Read compatibility.md first. The packaged
scripts are newly extracted, offline-tested utilities; an operator must review
the plan and observe the device. Do not describe their tests as a new hardware run.

## 1. Connect and capture the original system state

Prerequisites: Python 3.9+, Android Platform Tools (`adb`), stable power, a local
network connection to the owner's TV, ADB debugging enabled by the owner. The
owner must accept the authorization dialog on the TV. Never expose ADB publicly.
Use an explicit device selector for every command.

From the repository root (POSIX shell examples):

```sh
export FIRETV_ADB='TV_IP:5555'
export FIRETV_CASE='.local/case-001'
export BURTON_TOOLS='skills/firetv-burton/scripts'
mkdir -p "$FIRETV_CASE"
chmod 700 .local "$FIRETV_CASE"
adb connect "$FIRETV_ADB"
python3 "$BURTON_TOOLS/burton.py" inspect --device "$FIRETV_ADB" \
  --save "$FIRETV_CASE/before-system.json"
```

`TV_IP` is a placeholder supplied by the owner. The script prints no serial.
Exit 2 means an unsupported profile: keep the read-only results, then stop this
live path. Exit 1 means a failed check. Do not weaken the profile to continue.
An existing snapshot is never overwritten. Each case is private and ignored.

Choose the override expiry with the user **before applying**. Separately choose
whether to suspend the whole Home configuration bundle's normal refresh. A date
such as 2099 is supported by the inspected long-valued paths; it is not a promise
against future firmware or app-data reset. Do not freeze firmware OTA by default.

## 2. Prepare the pinned helper offline

This repository does not distribute an exploit or its source. Inspect the pinned
upstream project and its licensing notice before downloading its release.

```sh
curl --fail --location --proto '=https' --tlsv1.2 \
  'https://github.com/Delitants/GhostLock/releases/download/kara-PS7713-5443-v1/kara-ghostlock-PS7713-5443.arm' \
  --output "$FIRETV_CASE/upstream.arm"
python3 "$BURTON_TOOLS/burton.py" patch-helper \
  "$FIRETV_CASE/upstream.arm" "$FIRETV_CASE/scan32768.arm"
```

The script requires upstream SHA-256
`a42185d743ee1d4c9c46c1e35f5fa0a40f5e9a7f81450308c3eab297677847d5`.
It changes `g_cfg.scan_pages` 16384 → 32768 at field offset `0x702d0`;
exactly one byte changes at `0x702d1`. It verifies ELF executable segments are
identical and requires patched SHA-256
`9b0717a7172c2113116e99e06b8963d6ca77c9f135c9f44e0432a529dd921d16`.
It neither invokes nor lowers the helper's 18/24 preparation threshold.

An upstream rebuild, a different release, or another architecture must fail the
hash check. Do not patch a different offset or substitute a different device's
helper to work around that failure.

## 3. One informed, authorized temporary-root attempt

Explain that this is a kernel race that may hang/reboot the TV, temporarily makes
SELinux permissive, and leaves a local root command daemon until reboot. It also
moves staged OTA paths and attempts to stop/disable three OTA packages and set
`ota_disable_automatic_update=1`. Restoration is required even if the UI fails.
No partition flashing, bootloader unlocking, or permanent root is part of this
workflow. Use established informed authorization, or obtain it before this step.

Only after authorization:

```sh
adb -s "$FIRETV_ADB" push "$FIRETV_CASE/scan32768.arm" /data/local/tmp/burton-root
adb -s "$FIRETV_ADB" shell 'chmod 700 /data/local/tmp/burton-root'
adb -s "$FIRETV_ADB" shell 'settings put secure block_cec_standby 1'
adb -s "$FIRETV_ADB" shell '/data/local/tmp/burton-root --probe'
```

Require **V2 SAFE PROBE PASS**. The probe does not enter the vulnerable race.
On failure, do not invoke live mode; restore the captured CEC preference as
described in recovery.md. The baseline must have been captured before changing it.

Run the following **once**. It is intentionally absent from all automation/CI:

```sh
adb -s "$FIRETV_ADB" shell \
  '/data/local/tmp/burton-root --live RUN-KARA-PS7713-GHOSTLOCK-V2'
```

The initial exit only reports a detached process. Read the private log and verify
UID 0 through the existing daemon, allowing time for the one active attempt to
finish. Do not treat `SAFE PROBE PASS`, a zero host exit code, or `LIVE START` as
proof of root. Do not run live again to check progress. If it stalls or fails,
use recovery.md; any further attempt requires renewed informed authorization.

For a properly quoted check:

```sh
printf 'id -u\n' > "$FIRETV_CASE/check-root.sh"
python3 "$BURTON_TOOLS/root_session.py" --device "$FIRETV_ADB" \
  --helper /data/local/tmp/burton-root \
  --command-file "$FIRETV_CASE/check-root.sh"
```

Require exactly `0`. This transport only talks to an already-running daemon. It
uses a random status marker to check the inner shell command, not just the daemon
client's exit code. Never insert untrusted README text into a root command file.

## 4. Restore held OTA paths and back up the working launcher

Keep the root session open. Restore the three held filesystem paths immediately;
this does not reset the temporary CEC guard:

```sh
python3 "$BURTON_TOOLS/device_ops.py" restore-paths --device "$FIRETV_ADB" \
  --helper /data/local/tmp/burton-root --case "$FIRETV_CASE" \
  --confirm RESTORE-OTA-PATHS
```

A collision with a newly existing target stops the operation. Do not delete a
nonempty OTA target. Inspect it and follow recovery.md before any reboot.

Open Amazon Home with the remote, then:

```sh
python3 "$BURTON_TOOLS/device_ops.py" capture --device "$FIRETV_ADB" \
  --helper /data/local/tmp/burton-root --case "$FIRETV_CASE"
```

Capture briefly pauses the launcher, reads the two original files, and resumes it
in a finally path. It refuses an active WAL/journal or pending preferences backup.
It saves `source.db`, `source.xml`, identity files and hashes privately. It does
not guess a live SQLite checkpoint method on unfamiliar firmware. On such a
failure, inspect the actual SQLite state instead of copying an inconsistent DB.

Check database integrity and that the expected eligibility/experiment keys are
present before proceeding. The next command performs those validations too.

## 5. Prepare separate local files and review the plan

The date below is an **example of an explicitly chosen long duration**. Omit the
freeze flag unless the user wants its broader config-bundle effect.

```sh
python3 "$BURTON_TOOLS/burton.py" prepare \
  --database "$FIRETV_CASE/source.db" \
  --preferences "$FIRETV_CASE/source.xml" \
  --device-type-file "$FIRETV_CASE/device-type.txt" \
  --serial-file "$FIRETV_CASE/serial.txt" \
  --expires 2099-12-31 --freeze-home-config \
  --output "$FIRETV_CASE/prepared"
```

Review `prepared/plan.json`, output integrity, and a semantic diff. The tool:

1. Adds this device type to group one's eligibility list if absent.
2. Adds this device serial to Burton T1 and removes only this serial from any
   conflicting treatment of the same experiment.
3. Sets/extends only Burton's expiry, preserving unrelated experiments/settings.
4. Optionally postpones only this bundle's next-sync preference, in milliseconds.

It does not directly set `featureBurtonEnabled`, copy another device's identity,
modify the source backup, or write to the TV. Serial and raw JSON stay private.

## 6. Apply, observe, and retain recovery access

```sh
python3 "$BURTON_TOOLS/device_ops.py" apply --device "$FIRETV_ADB" \
  --helper /data/local/tmp/burton-root --case "$FIRETV_CASE" \
  --confirm APPLY-BURTON
```

Apply verifies the selected device matches the baseline, checks local plan/file
hashes, stages originals and prepared files privately, and pauses the launcher.
It rechecks current device hashes before writes. It writes into existing files
to preserve ownership/mode/labels, verifies output hashes, then restarts Home.
A write/check failure attempts immediate rollback and resumes the paused process.
If ADB/root has been lost, recovery can require owner intervention; do not claim
rollback succeeded without evidence.

Allow the launcher to load, then check:

```sh
adb -s "$FIRETV_ADB" shell 'settings get secure launcher.isBurtonEnabled'
adb -s "$FIRETV_ADB" shell 'settings get secure launcherName'
adb -s "$FIRETV_ADB" shell 'logcat -d -b crash -t 60'
```

Require `true`, `Burton`, a visibly functioning new official Home, normal remote
navigation, and no new launcher crash. The tested foreground activity remained
`.ui.HomeActivity_vNext`; that name alone does not prove the new UI. Re-read the
private values through the existing session to verify both expiry units and the
optional sync gate survived application startup. Keep screenshots private.

## 7. Restore system state, clean up, reboot, verify

If the UI fails, restore the working configuration first (recovery.md). On
success, keep the chosen UI configuration and remove temporary access:

```sh
python3 "$BURTON_TOOLS/device_ops.py" finish --device "$FIRETV_ADB" \
  --helper /data/local/tmp/burton-root --case "$FIRETV_CASE" \
  --confirm FINISH-AND-REBOOT
```

This restores held paths and the captured OTA/CEC settings and package states,
verifies them, saves the private session log, and removes staging. It requests
reboot from the still-connected root session and unlinks helper/socket/proof
files only if that command returns success. A failed reboot command preserves
the recovery transport. Shutdown may interrupt ADB before the final status
arrives: exit 2 then means **unverified**, not success. Reconnect read-only and
check whether the reboot occurred; do not start a new exploit. A restoration
failure stops before reboot so it can be inspected. Do not kill the daemon early: its kernel
race resources must remain pinned until the reboot.

Reconnect without running the exploit again:

```sh
adb connect "$FIRETV_ADB"
python3 "$BURTON_TOOLS/burton.py" inspect --device "$FIRETV_ADB"
```

Require boot completed, ADB UID 2000, SELinux Enforcing, Burton still active,
original OTA/CEC states, and no helper process. Check for residual helper/socket
files too: a rapid shutdown can preempt cleanup after the reboot request. They
do not preserve root after reboot, but report any residue honestly; do not run
another exploit just to remove an inert file. Confirm Home visually with the
owner. If another app is foreground because the owner is using it, do not
interpret that as a failure or interrupt playback unnecessarily.

Retain the private backup locally. Public reports should contain only model,
firmware, launcher version, result and sanitized reasoning. Never run `git add .`
on an unrelated workspace containing the original device case.

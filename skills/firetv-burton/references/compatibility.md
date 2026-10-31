# Compatibility, mechanism and evidence

## Verified live case — 31 October 2026

| Property | Tested value |
| --- | --- |
| Product | Fire TV Stick 4K Max, first generation (2021) |
| Model / codename | AFTKA / kara |
| Fire OS | 7.7.1.3, PS7713/5443 |
| Incremental build | `0035334210436` |
| Android / userspace | API 28 / 32-bit ARM, `armv7l` |
| Kernel / CPUs | `4.14.87+` / `0-3` |
| Stock Amazon launcher | `com.amazon.tv.launcher`, 7280112.1, code 728011210 |
| Result | Burton UI rendered, navigation worked, persisted across reboot; owner confirmed |

One owned device was tested. This is not evidence that every Fire TV or every
Fire OS 7 build works. The packaged utilities were subsequently extracted and
tested offline; they have not been separately exercised as a complete new live
installation. Treat the runbook as an operator-assisted research workflow.

## Why the existing launcher can work

The original signed launcher already includes Burton UI code. Its
`BurtonDeviceEligibilityMapper` checks `ro.product.config.type` against the
`eligibleBurtonDeviceTypes` arrays. Group one uses experiment
`FTV_BURTON_R26_1325767`; treatment `T1` enables the feature.

`MobileWeblabClientManager` supports local `weblabOverrides` in the launcher's
Arcus configuration. Each experiment has `expiryUtc` (Unix **seconds**) and
`treatments` mapping treatment names to arrays of device serials. The real serial
must match the value the launcher reads (`Build.SERIAL` on this firmware).

Relevant database: private launcher `databases/` directory, filename
`arn:aws:remote-config:us-west-2:541693914820:appConfig:aoio3k0i_ConfigurationCache.db`.
Table `configuration` contains `_id`, `json`, `origin`, `timestamp`, `entity_tag`.
The tested database had one remote row, origin 2. Discover and validate the
actual file and schema; do not create a guessed database on an untested build.

The application writes `featureBurtonEnabled=true` in its default preferences
and writes secure settings `launcher.isBurtonEnabled=true`, `launcherName=Burton`
after accepting the feature. Those settings are useful verification outputs.

## Optional refresh freeze

Default preferences file: `shared_prefs/com.amazon.tv.launcher_preferences.xml`.
The `<long>` named
`arn:aws:remote-config:us-west-2:541693914820:appConfig:aoio3k0iNextSyncTimeInMillis`
controls the next normal fetch for that bundle. `ArcusConfigManager.syncIfNeeded`
fetches only when `currentTimeMillis() > savedTime`; otherwise it keeps the cache
and schedules a later check using a Java `long` delay.

The optional freeze sets this value to the chosen future date in Unix
**milliseconds**. `expiryUtc` is parsed as a Java `long` in seconds, so 2099 fits
the inspected paths. This freezes the entire `aoio3k0i` bundle, including other
Home behavior parameters. Other bundles and firmware OTA are separate. A future
app/firmware update or clearing app data can remove this protection.

## What failed and what it establishes

- Official APK 7313002.1 installed with the correct Amazon certificate, but
  crashed because system `com.amazon.tv.ftvkarmalibrary` lacked enum field
  `AlexaExperience.SEARCH_ONLY`. API/CPU/signature matching alone is insufficient.
- Rebuilding an Amazon APK loses its original signature. Renaming a rebuilt APK
  also loses the original app identity/privileged integrations. Neither is the
  method documented here; Amazon APKs and framework files are not distributed.
- `run-as` was denied because the launcher is not debuggable. Its exported
  Compose PreviewActivity also rejects a non-debuggable app.
- Home-button accessibility/AlarmManager techniques in third-party launcher
  projects solve routing delays, not this private feature activation.
- The stock temporary-root helper stopped twice before its vulnerable call at
  a 17/24 preparation score. A separate no-trigger diagnostic with the original
  scan width was inconclusive; doubling scan pages produced a unique 24/24.
- The hash-pinned one-byte scan-data patch then obtained temporary root. A later
  separately authorized session also succeeded. This is not a guarantee that a
  future attempt will succeed. No safety threshold was lowered.

## Provenance

- [GhostLock kara source, pinned commit](https://github.com/Delitants/GhostLock/tree/5a9e2b08d0dca369df442c612a2693d3e7a771c6/kara)
- [Original release](https://github.com/Delitants/GhostLock/releases/tag/kara-PS7713-5443-v1)
- [Upstream provenance and licensing boundary](https://github.com/Delitants/GhostLock/blob/5a9e2b08d0dca369df442c612a2693d3e7a771c6/kara/PROVENANCE.md)
- [Related exact-device controller](https://github.com/Delitants/firetv-kara-standalone)
- [Home routing example](https://github.com/NikhilSiddhu/firetv-tvos)
- [Independent custom launcher example](https://github.com/jeremykenedy/fire-tv-ui)

The conclusions above combine local SDK disassembly and observations on the
owned device. These are a sanitized case report, not an Amazon support statement
or a claim of inclusion in Amazon's official rollout. Private logs, identities,
databases, APKs and screenshots are intentionally absent.

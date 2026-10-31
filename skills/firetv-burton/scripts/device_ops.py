#!/usr/bin/env python3
"""Reviewed mutations through an existing authorized root session. No exploit runner.

The manual hardware procedure is documented separately. These extracted utilities
have offline tests, not a separate end-to-end live qualification.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

from burton import Adb, APP_CONFIG, OTA_PACKAGES, TARGET, dump, private_write, require, sha
from root_session import RootSession, TransportStatusUnknown

APP = '/data/data/com.amazon.tv.launcher'
DB = APP + '/databases/' + APP_CONFIG + '_ConfigurationCache.db'
PREFS = APP + '/shared_prefs/com.amazon.tv.launcher_preferences.xml'
HELD_PATHS = (
    ('/data/local/tmp/kara-ota-package.PS7713-held', '/data/ota_package'),
    ('/cache/recovery/command.kara-PS7713-held', '/cache/recovery/command'),
    ('/cache/recovery/block.map.kara-PS7713-held', '/cache/recovery/block.map'))


def launcher_pids(session):
    pids = session.run('pidof com.amazon.tv.launcher').decode().strip().split()
    require(bool(pids) and all(p.isdecimal() for p in pids), 'Open Home before capture/apply')
    return ' '.join(pids)


def assert_quiet(session):
    session.run('test ! -s ' + shlex.quote(DB + '-wal') + '\n'
                'test ! -s ' + shlex.quote(DB + '-journal') + '\n'
                'test ! -e ' + shlex.quote(PREFS + '.bak'))


def state_for_case(case, adb, require_launcher=True):
    state = json.loads((case / 'before-system.json').read_text())
    require(state.get('supported') is True and all(state.get(k) == v for k, v in TARGET.items()),
            'An exact supported baseline is required')
    require(state.get('uid') == '2000' and state.get('selinux') == 'Enforcing',
            'Baseline must precede temporary root')
    current = adb.inspect()
    for key, expected in TARGET.items():
        if key == 'launcher_version_code' and not require_launcher:
            continue  # Recovery must remain available if the launcher itself changed.
        require(current.get(key) == expected, 'Current device profile changed: ' + key)
    require(current['device_id_sha256'] == state['device_id_sha256'],
            'Backup belongs to a different device')
    return state


def capture(case, session):
    require(not (case / 'capture.json').exists(), 'Never overwrite the working backup')
    for name in ('source.db', 'source.xml', 'serial.txt', 'device-type.txt'):
        require(not (case / name).exists(), 'Capture files already exist; inspect this case')
    pids = launcher_pids(session)
    try:
        session.run('kill -STOP ' + pids)
        assert_quiet(session)
        db, prefs = session.run('cat ' + shlex.quote(DB)), session.run('cat ' + shlex.quote(PREFS))
        attrs = session.run('stat -c "%u %g %a" ' + shlex.quote(DB) + ' ' + shlex.quote(PREFS)).decode()
        private_write(case / 'source.db', db)
        private_write(case / 'source.xml', prefs)
    finally:
        session.run('kill -CONT ' + pids)
    private_write(case / 'serial.txt', session.run('getprop ro.serialno'))
    private_write(case / 'device-type.txt', session.run('getprop ro.product.config.type'))
    dump(case / 'capture.json', {'id': uuid.uuid4().hex,
         'database_sha256': sha(db), 'preferences_sha256': sha(prefs), 'original_attrs': attrs})


def stage_name(case):
    identity = json.loads((case / 'capture.json').read_text())['id']
    require(bool(re.fullmatch(r'[0-9a-f]{32}', identity)), 'Invalid case identity')
    return '/data/local/tmp/burton-' + identity


def remote_hashes(session):
    lines = session.run('sha256sum ' + shlex.quote(DB) + ' ' + shlex.quote(PREFS)).decode().splitlines()
    require(len(lines) == 2, 'Unexpected hash response')
    return [line.split()[0] for line in lines]


def apply(case, session, adb):
    require(not (case / 'applied.json').exists(), 'Case was already applied; do not replay it')
    plan = json.loads((case / 'prepared/plan.json').read_text())
    require(plan['profile'] == TARGET, 'Unsupported plan')
    source_files = [case / 'source.db', case / 'source.xml']
    new_files = [case / 'prepared/configuration.db', case / 'prepared/preferences.xml']
    old_hashes = [sha(p.read_bytes()) for p in source_files]
    new_hashes = [sha(p.read_bytes()) for p in new_files]
    require(old_hashes == [plan['source_db_sha256'], plan['source_preferences_sha256']], 'Source changed')
    require(new_hashes == [plan['configuration_sha256'], plan['preferences_sha256']], 'Prepared files changed')
    staging = stage_name(case)
    adb.shell('mkdir ' + shlex.quote(staging) + ' && chmod 700 ' + shlex.quote(staging))
    for path in source_files + new_files:
        subprocess.run([adb.executable, '-s', adb.device, 'push', str(path), staging + '/'],
                       check=True, timeout=30, capture_output=True)
    pids = launcher_pids(session)
    wrote = False
    completed = False
    try:
        session.run('kill -STOP ' + pids)
        assert_quiet(session)
        require(remote_hashes(session) == old_hashes, 'Device files changed: refresh backup before applying')
        # Set before the first write so a failure during either write triggers rollback.
        wrote = True
        session.run('cat ' + shlex.quote(staging + '/configuration.db') + ' > ' + shlex.quote(DB) + '\n'
                    'cat ' + shlex.quote(staging + '/preferences.xml') + ' > ' + shlex.quote(PREFS) + '\nsync')
        require(remote_hashes(session) == new_hashes, 'Device write verification failed')
        session.run('kill -KILL ' + pids)
        completed = True
    except Exception:
        if wrote:
            session.run('cat ' + shlex.quote(staging + '/source.db') + ' > ' + shlex.quote(DB) + '\n'
                        'cat ' + shlex.quote(staging + '/source.xml') + ' > ' + shlex.quote(PREFS) + '\nsync')
        raise
    finally:
        if not completed:
            session.run('kill -CONT ' + pids)
    dump(case / 'applied.json', {'configuration_sha256': new_hashes[0], 'preferences_sha256': new_hashes[1]})
    adb.shell('input keyevent 3')


def restore_held_paths(session):
    for held, original in HELD_PATHS:
        session.run('if [ -e ' + shlex.quote(held) + ' ]; then\n'
                    '  test ! -e ' + shlex.quote(original) + '\n'
                    '  mv ' + shlex.quote(held) + ' ' + shlex.quote(original) + '\nfi')


def restore_system(case, session, adb):
    state = state_for_case(case, adb, require_launcher=False)
    restore_held_paths(session)
    states = {0: 'default-state', 1: 'enable', 2: 'disable', 3: 'disable-user', 4: 'disable-until-used'}
    for package in OTA_PACKAGES:
        saved = state['ota_enabled_before'][package]
        require(saved in states, 'Unknown saved package state')
        session.run('runcon u:r:shell:s0 /system/bin/pm ' + states[saved] + ' --user 0 ' + package)
    for namespace, key, value in [('secure', 'block_cec_standby', state['cec_before']),
                                  ('global', 'ota_disable_automatic_update', state['ota_global_before'])]:
        if value == 'null':
            adb.shell('settings delete ' + namespace + ' ' + key)
        else:
            adb.shell('settings put ' + namespace + ' ' + key + ' ' + shlex.quote(value))
    session.run('sync')
    now = adb.inspect()
    require(now['cec_before'] == state['cec_before'] and now['ota_global_before'] == state['ota_global_before']
            and now['ota_enabled_before'] == state['ota_enabled_before'], 'System state restoration incomplete')


def finish(case, session, adb):
    restore_system(case, session, adb)
    log_path = case / 'root-session.log'
    if not log_path.exists():
        private_write(log_path, session.run('cat /data/local/tmp/kara-ghostlock.log'))
    cleanup = []
    if (case / 'capture.json').exists():
        staging = stage_name(case)
        for name in ('source.db', 'source.xml', 'configuration.db', 'preferences.xml'):
            cleanup.append('rm -f ' + shlex.quote(staging + '/' + name))
        cleanup.append('if [ -d ' + shlex.quote(staging) + ' ]; then rmdir ' + shlex.quote(staging) + '; fi')
    cleanup.append('sync')
    session.run('\n'.join(cleanup))
    # Keep the helper and socket until the reboot command has been accepted.
    # RootSession's set -e stops before unlinking them if reboot returns failure.
    final_command = ('runcon u:r:shell:s0 /system/bin/reboot\n'
                     'rm -f /data/local/tmp/kara-root-ready /data/local/tmp/kara-root.sock '
                     '/data/local/tmp/kara-ghostlock.log ' + shlex.quote(session.helper) + '\nsync')
    try:
        session.run(final_command)
    except (TransportStatusUnknown, subprocess.SubprocessError):
        # Shutdown can stop adbd before the status marker arrives. Do not report
        # success or start another root attempt; the next step is read-only proof.
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capture', 'apply', 'restore-paths', 'restore-system', 'finish'])
    parser.add_argument('--device', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--confirm', help='APPLY-BURTON or RESTORE-SYSTEM or FINISH-AND-REBOOT')
    args = parser.parse_args()
    try:
        required = {'apply': 'APPLY-BURTON', 'restore-paths': 'RESTORE-OTA-PATHS', 'restore-system': 'RESTORE-SYSTEM',
                    'finish': 'FINISH-AND-REBOOT'}
        if args.action in required:
            require(args.confirm == required[args.action], 'Read the plan and provide the explicit confirmation token')
        adb = Adb(args.device, args.adb)
        state_for_case(args.case, adb, require_launcher=args.action in ('capture', 'apply'))
        session = RootSession(args.device, args.helper, args.adb)
        if args.action == 'capture': capture(args.case, session)
        if args.action == 'apply': apply(args.case, session, adb)
        if args.action == 'restore-paths': restore_held_paths(session)
        if args.action == 'restore-system': restore_system(args.case, session, adb)
        if args.action == 'finish' and not finish(args.case, session, adb):
            print('Reboot command transport interrupted: completion UNVERIFIED. Reconnect read-only; do not rerun live.', file=sys.stderr)
            return 2
        print('Completed:', args.action, '- follow the workflow verification step.')
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('STOP:', exc, file=sys.stderr)
        print('Keep the working session if available. Read references/recovery.md; do not rerun live.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

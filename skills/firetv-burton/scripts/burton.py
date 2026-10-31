#!/usr/bin/env python3
"""Offline Burton preparation and read-only ADB inspection. Python 3.9+, stdlib.

This module never starts a root exploit and never writes to an Android device.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import struct
import subprocess
import sys
from urllib.parse import quote
import xml.etree.ElementTree as ET

LAB = 'FTV_BURTON_R26_1325767'
ELIGIBLE = 'eligibleBurtonDeviceTypes'
APP_CONFIG = 'arn:aws:remote-config:us-west-2:541693914820:appConfig:aoio3k0i'
SYNC_KEY = APP_CONFIG + 'NextSyncTimeInMillis'
ORIGINAL_HASH = 'a42185d743ee1d4c9c46c1e35f5fa0a40f5e9a7f81450308c3eab297677847d5'
PATCHED_HASH = '9b0717a7172c2113116e99e06b8963d6ca77c9f135c9f44e0432a529dd921d16'
TARGET = {'device': 'kara', 'model': 'AFTKA', 'build': '0035334210436',
          'sdk': '28', 'kernel': '4.14.87+', 'machine': 'armv7l', 'cpus': '0-3',
          'launcher_version_code': '728011210'}
OTA_PACKAGES = ('com.amazon.device.software.ota',
                'com.amazon.device.software.ota.override',
                'com.amazon.tv.forcedotaupdater.v2')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(data)


def dump(path, value):
    private_write(path, (json.dumps(value, indent=2) + '\n').encode())


def readonly_db(path):
    return sqlite3.connect('file:' + quote(str(Path(path).resolve()), safe='/') + '?mode=ro', uri=True)


def expiry_seconds(value):
    day = dt.date.fromisoformat(value)
    expiry = int(dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp())
    require(expiry > int(dt.datetime.now(dt.timezone.utc).timestamp()), 'Expiry must be in the future')
    return expiry


def transform_config(config, device_type, serial, expiry):
    require(isinstance(config, dict) and isinstance(config.get(ELIGIBLE), list),
            'Unrecognized launcher config; do not guess its schema')
    require(all(isinstance(v, str) for v in config[ELIGIBLE]), 'Invalid eligibility array')
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', device_type)), 'Invalid device type')
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', serial)), 'Invalid serial')
    result = copy.deepcopy(config)
    if device_type not in result[ELIGIBLE]:
        result[ELIGIBLE].append(device_type)
    overrides = result.setdefault('weblabOverrides', {})
    require(isinstance(overrides, dict), 'Invalid overrides')
    lab = overrides.setdefault(LAB, {'expiryUtc': str(expiry), 'treatments': {}})
    require(isinstance(lab, dict) and isinstance(lab.get('treatments'), dict), 'Invalid Burton override')
    previous = lab.get('expiryUtc', 0)
    renewed = max(int(previous), expiry)
    lab['expiryUtc'] = str(renewed) if isinstance(previous, str) else renewed
    for treatment, members in lab['treatments'].items():
        require(isinstance(members, list) and all(isinstance(v, str) for v in members),
                'Invalid treatment members')
        if treatment != 'T1':
            lab['treatments'][treatment] = [v for v in members if v != serial]
    members = lab['treatments'].setdefault('T1', [])
    if serial not in members:
        members.append(serial)
    return result


def preference_values(raw):
    root = ET.fromstring(raw)
    require(root.tag == 'map', 'Expected Android SharedPreferences map')
    names = [e.attrib.get('name') for e in root]
    require(None not in names and len(names) == len(set(names)), 'Duplicate or missing preference name')
    return {e.attrib['name']: ET.tostring(e, encoding='unicode') for e in root}


def set_sync(raw, millis):
    before = preference_values(raw)
    pattern = r'(<long\s+name="' + re.escape(SYNC_KEY) + r'"\s+value=")[0-9]+("\s*/>)'
    result, count = re.subn(pattern, lambda m: m[1] + str(millis) + m[2], raw)
    require(count == 1, 'Expected exactly one known long-valued sync preference')
    after = preference_values(result)
    require(set(before) == set(after), 'Preference names changed unexpectedly')
    require(all(before[k] == after[k] for k in before if k != SYNC_KEY),
            'An unrelated preference changed')
    return result


def prepare(database, preferences, device_type, serial, expires, output, freeze):
    output = Path(output)
    require(not output.exists(), 'Output already exists; keep the original backup')
    require(not Path(str(database) + '-wal').exists(),
            'Use a coherent, closed SQLite snapshot; a WAL sibling is present')
    expiry = expiry_seconds(expires)
    raw_prefs = Path(preferences).read_text()
    preference_values(raw_prefs)
    prefs_out = set_sync(raw_prefs, expiry * 1000) if freeze else raw_prefs
    with readonly_db(database) as src:
        require(src.execute('PRAGMA integrity_check').fetchone() == ('ok',), 'Invalid source database')
        rows = src.execute('SELECT _id,json FROM configuration').fetchall()
        changes = []
        for row_id, raw in rows:
            config = json.loads(raw)
            if isinstance(config, dict) and ELIGIBLE in config:
                updated = transform_config(config, device_type, serial, expiry)
                # Explicit preservation contract, beyond copying a dict.
                require(all(config[k] == updated[k] for k in config
                            if k not in (ELIGIBLE, 'weblabOverrides')), 'Unexpected config change')
                require(all(v == updated['weblabOverrides'][k]
                            for k, v in config.get('weblabOverrides', {}).items() if k != LAB),
                        'Another experiment changed')
                changes.append((json.dumps(updated, separators=(',', ':')), row_id))
        require(len(changes) == 1, 'Expected exactly one launcher configuration row')
        output.mkdir(parents=True, mode=0o700)
        db_out = output / 'configuration.db'
        private_write(db_out, b'')
        with sqlite3.connect(db_out) as dst:
            src.backup(dst)
            dst.executemany('UPDATE configuration SET json=? WHERE _id=?', changes)
            require(dst.execute('PRAGMA integrity_check').fetchone() == ('ok',), 'Invalid prepared database')
        # Avoid shipping host-side WAL state to a device as a single-file DB.
        with sqlite3.connect(db_out) as dst:
            dst.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            dst.execute('PRAGMA journal_mode=DELETE')
    private_write(output / 'preferences.xml', prefs_out.encode())
    dump(output / 'plan.json', {'profile': TARGET, 'experiment': LAB,
         'expires_utc': expires, 'freeze_bundle': bool(freeze),
         'source_db_sha256': sha(Path(database).read_bytes()),
         'source_preferences_sha256': sha(Path(preferences).read_bytes()),
         'configuration_sha256': sha(db_out.read_bytes()),
         'preferences_sha256': sha((output / 'preferences.xml').read_bytes()),
         'changes': ['Burton eligibility and T1 override'] + ([SYNC_KEY] if freeze else [])})
    return output


def executable_segments(data):
    require(data[:6] == b'\x7fELF\x01\x01', 'Expected little-endian ELF32')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phsize, phcount = struct.unpack_from('<HH', data, 42)
    require(phsize == 32, 'Unexpected ELF program header size')
    segments = []
    for i in range(phcount):
        ptype, offset, _va, _pa, length, _mem, flags, _align = struct.unpack_from('<8I', data, phoff + i * phsize)
        if ptype == 1 and flags & 1:
            segments.append(data[offset:offset + length])
    require(bool(segments), 'No executable ELF segment')
    return segments


def patch_helper(source, output):
    data = Path(source).read_bytes()
    require(sha(data) == ORIGINAL_HASH, 'Wrong upstream artifact: refusing binary patch')
    require(struct.unpack_from('<I', data, 0x702d0)[0] == 16384, 'Unexpected scan parameter')
    patched = bytearray(data)
    struct.pack_into('<I', patched, 0x702d0, 32768)
    require([i for i, (a, b) in enumerate(zip(data, patched)) if a != b] == [0x702d1],
            'Unexpected patch difference')
    require(executable_segments(data) == executable_segments(patched), 'Executable code changed')
    require(sha(patched) == PATCHED_HASH, 'Unexpected patched digest')
    private_write(output, patched)
    Path(output).chmod(0o700)


class Adb:
    def __init__(self, device, executable='adb'):
        require(bool(device) and not device.startswith('-'), 'Select one explicit ADB device')
        self.device, self.executable = device, executable

    def shell(self, command):
        # ADB joins arguments for a remote shell: pass ONE already-quoted command.
        return subprocess.run([self.executable, '-s', self.device, 'shell', command],
                              capture_output=True, timeout=30, check=True).stdout.decode().strip()

    def inspect(self):
        commands = {'device': 'getprop ro.product.device', 'model': 'getprop ro.product.model',
                    'build': 'getprop ro.build.version.incremental', 'sdk': 'getprop ro.build.version.sdk',
                    'kernel': 'uname -r', 'machine': 'uname -m',
                    'cpus': 'cat /sys/devices/system/cpu/online'}
        result = {k: self.shell(v) for k, v in commands.items()}
        package = self.shell('dumpsys package com.amazon.tv.launcher')
        version = re.search(r'\bversionCode=(\d+)', package)
        result['launcher_version_code'] = version.group(1) if version else ''
        result['supported'] = all(result[k] == v for k, v in TARGET.items())
        result['mismatches'] = [k for k, v in TARGET.items() if result[k] != v]
        result['uid'] = self.shell('id -u')
        result['selinux'] = self.shell('getenforce')
        result['burton'] = self.shell('settings get secure launcher.isBurtonEnabled')
        result['launcher_name'] = self.shell('settings get secure launcherName')
        result['device_id_sha256'] = sha(self.shell('getprop ro.serialno').encode())
        result['cec_before'] = self.shell('settings get secure block_cec_standby')
        result['ota_global_before'] = self.shell('settings get global ota_disable_automatic_update')
        result['ota_enabled_before'] = {}
        for name in OTA_PACKAGES:
            text = self.shell('dumpsys package ' + shlex.quote(name))
            match = re.search(r'User 0:.*\benabled=(\d+)', text)
            require(match is not None, 'Could not read OTA package state: ' + name)
            result['ota_enabled_before'][name] = int(match.group(1))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    inspect = commands.add_parser('inspect', help='Read-only device inspection; no root')
    inspect.add_argument('--device', required=True)
    inspect.add_argument('--adb', default='adb')
    inspect.add_argument('--save', type=Path)
    patch = commands.add_parser('patch-helper', help='Offline, hash-pinned scan-parameter patch')
    patch.add_argument('source', type=Path)
    patch.add_argument('output', type=Path)
    prep = commands.add_parser('prepare', help='Prepare separate local files; never writes to a device')
    prep.add_argument('--database', required=True, type=Path)
    prep.add_argument('--preferences', required=True, type=Path)
    prep.add_argument('--device-type-file', required=True, type=Path)
    prep.add_argument('--serial-file', required=True, type=Path)
    prep.add_argument('--expires', required=True, help='UTC date YYYY-MM-DD, chosen with the user')
    prep.add_argument('--freeze-home-config', action='store_true', help='Suspend the entire Home config bundle refresh')
    prep.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'inspect':
            state = Adb(args.device, args.adb).inspect()
            if args.save:
                require(state['uid'] == '2000' and state['selinux'] == 'Enforcing',
                        'Capture baseline BEFORE temporary root')
                dump(args.save, state)
            print(json.dumps(state, indent=2))
            return 0 if state['supported'] else 2
        if args.action == 'patch-helper':
            patch_helper(args.source, args.output)
            print('Verified one-byte data patch; executable segments unchanged. No code executed.')
        if args.action == 'prepare':
            prepare(args.database, args.preferences, args.device_type_file.read_text().strip(),
                    args.serial_file.read_text().strip(), args.expires, args.output, args.freeze_home_config)
            print('Prepared separate files. Read plan.json before any device mutation.')
        return 0
    except (ValueError, OSError, sqlite3.Error, ET.ParseError, subprocess.SubprocessError) as exc:
        print('STOP:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

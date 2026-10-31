import copy
import hashlib
import json
from pathlib import Path
import shlex
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/firetv-burton/scripts'
sys.path.insert(0, str(SCRIPTS))
import burton
import device_ops
from root_session import RootSession


def config():
    return {'eligibleBurtonDeviceTypes': ['OTHER_TYPE'], 'unrelated': {'nested': [1, 2]},
            'weblabOverrides': {
                'OTHER_EXPERIMENT': {'expiryUtc': '9999999999', 'treatments': {'T2': ['OTHER_SERIAL']}},
                burton.LAB: {'expiryUtc': '1', 'treatments': {'C': ['TEST_SERIAL', 'KEEP_SERIAL'],
                                                         'T1': ['OTHER_SERIAL']}}}}


def prefs():
    return ('<?xml version="1.0" encoding="utf-8"?>\n<map>\n'
            '<string name="unrelated">keep &amp; preserve</string>\n'
            '<boolean name="featureBurtonEnabled" value="false" />\n'
            '<long name="' + burton.SYNC_KEY + '" value="123" />\n</map>\n')


def make_case(path):
    database = path / 'source.db'
    con = sqlite3.connect(database)
    con.execute('CREATE TABLE configuration (_id INTEGER PRIMARY KEY, json TEXT, origin INTEGER, timestamp INTEGER, entity_tag TEXT)')
    con.execute('INSERT INTO configuration VALUES (1, ?, 2, 1234, ?)', (json.dumps(config()), 'SYNTHETIC_ETAG'))
    con.commit(); con.close()
    (path / 'source.xml').write_text(prefs())
    (path / 'capture.json').write_text(json.dumps({'id': 'a' * 32}))
    return database


class ConfigTests(unittest.TestCase):
    def test_transform_preserves_other_devices_settings_and_experiments(self):
        old = config(); snapshot = copy.deepcopy(old)
        result = burton.transform_config(old, 'TEST_TYPE', 'TEST_SERIAL', 4102358400)
        self.assertEqual(old, snapshot)
        self.assertEqual(result['unrelated'], old['unrelated'])
        self.assertEqual(result['weblabOverrides']['OTHER_EXPERIMENT'], old['weblabOverrides']['OTHER_EXPERIMENT'])
        self.assertEqual(result['weblabOverrides'][burton.LAB]['treatments']['C'], ['KEEP_SERIAL'])
        self.assertEqual(result['weblabOverrides'][burton.LAB]['treatments']['T1'], ['OTHER_SERIAL', 'TEST_SERIAL'])
        self.assertEqual(result, burton.transform_config(result, 'TEST_TYPE', 'TEST_SERIAL', 4102358400))

    def test_new_lab_and_numeric_expiry(self):
        old = config(); del old['weblabOverrides'][burton.LAB]
        result = burton.transform_config(old, 'TEST_TYPE', 'TEST_SERIAL', 4102358400)
        self.assertEqual(result['weblabOverrides'][burton.LAB]['expiryUtc'], '4102358400')
        result['weblabOverrides'][burton.LAB]['expiryUtc'] = 4200000000
        newer = burton.transform_config(result, 'TEST_TYPE', 'TEST_SERIAL', 4102358400)
        self.assertEqual(newer['weblabOverrides'][burton.LAB]['expiryUtc'], 4200000000)

    def test_invalid_schema_is_rejected(self):
        for invalid in [[], {}, {'eligibleBurtonDeviceTypes': 'bad'},
                        {'eligibleBurtonDeviceTypes': [], 'weblabOverrides': []}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                burton.transform_config(invalid, 'TEST_TYPE', 'TEST_SERIAL', 4102358400)

    def test_freeze_preserves_all_other_xml_bytes(self):
        raw = prefs(); result = burton.set_sync(raw, 4102358400000)
        self.assertEqual(result, raw.replace('value="123"', 'value="4102358400000"'))
        self.assertEqual(burton.set_sync(result, 0), raw.replace('value="123"', 'value="0"'))
        self.assertEqual(burton.expiry_seconds('2099-12-31'), 4102358400)

    def test_duplicate_or_missing_sync_is_rejected(self):
        for raw in ['<map/>', prefs().replace('</map>', '<long name="' + burton.SYNC_KEY + '" value="1" /></map>')]:
            with self.assertRaises(ValueError): burton.set_sync(raw, 4102358400000)

    def test_sqlite_snapshot_source_and_metadata_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            original = database.read_bytes()
            burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', True)
            self.assertEqual(database.read_bytes(), original)
            with sqlite3.connect(path / 'prepared/configuration.db') as db:
                self.assertEqual(db.execute('SELECT _id,origin,timestamp,entity_tag FROM configuration').fetchone(),
                                 (1, 2, 1234, 'SYNTHETIC_ETAG'))
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            with self.assertRaises(ValueError):
                burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', True)

    def test_active_wal_refused_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            Path(str(database) + '-wal').write_bytes(b'not a coherent snapshot')
            with self.assertRaises(ValueError):
                burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', False)
            self.assertFalse((path / 'prepared').exists())

    def test_ambiguous_configuration_rows_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            with sqlite3.connect(database) as db:
                db.execute('INSERT INTO configuration SELECT 2,json,origin,timestamp,entity_tag FROM configuration')
            with self.assertRaises(ValueError):
                burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', False)
            self.assertFalse((path / 'prepared').exists())

    def test_no_freeze_keeps_preferences_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', False)
            self.assertEqual((path / 'source.xml').read_bytes(), (path / 'prepared/preferences.xml').read_bytes())


class HelperTests(unittest.TestCase):
    def test_unknown_binary_never_produces_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'source', Path(temp) / 'patched'
            source.write_bytes(b'unknown ELF')
            with self.assertRaises(ValueError): burton.patch_helper(source, output)
            self.assertFalse(output.exists())

    def test_synthetic_elf_one_byte_patch_preserves_code(self):
        data = bytearray(0x70300)
        data[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<I', data, 28, 52)
        struct.pack_into('<HH', data, 42, 32, 1)
        struct.pack_into('<8I', data, 52, 1, 0x100, 0, 0, 0x100, 0x100, 5, 0x1000)
        data[0x100:0x200] = bytes(range(256))
        struct.pack_into('<I', data, 0x702d0, 16384)
        expected = bytearray(data); struct.pack_into('<I', expected, 0x702d0, 32768)
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'source', Path(temp) / 'patched'
            source.write_bytes(data)
            with mock.patch.object(burton, 'ORIGINAL_HASH', burton.sha(data)), \
                 mock.patch.object(burton, 'PATCHED_HASH', burton.sha(expected)):
                burton.patch_helper(source, output)
            self.assertEqual(output.read_bytes(), expected)
            self.assertEqual(burton.executable_segments(data), burton.executable_segments(expected))


class TransportTests(unittest.TestCase):
    def test_remote_command_is_one_quoted_argument_and_binary_roundtrip(self):
        session = RootSession('DEVICE_PLACEHOLDER', '/data/local/tmp/helper', verify=False)
        payload = b'\x00\xffbinary\n\n'
        with mock.patch('root_session.secrets.token_hex', return_value='token'), \
             mock.patch('root_session.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, payload + b'\n__BURTON_STATUS_token__0\n', b'')
            self.assertEqual(session.run("printf 'a; b'; cat /private/path"), payload)
            arguments = run.call_args[0][0]
            parsed = shlex.split(arguments[-1])
            self.assertEqual(parsed[:2], ['/data/local/tmp/helper', '--cmd'])
            self.assertEqual(len(parsed), 3)
            self.assertIn("printf 'a; b'", parsed[2])

    def test_inner_failure_is_not_hidden_by_client_success(self):
        session = RootSession('DEVICE_PLACEHOLDER', '/data/local/tmp/helper', verify=False)
        with mock.patch('root_session.secrets.token_hex', return_value='token'), \
             mock.patch('root_session.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, b'denied\n__BURTON_STATUS_token__1\n', b'')
            with self.assertRaisesRegex(ValueError, 'Remote command failed'): session.run('false')
            run.return_value = subprocess.CompletedProcess([], 0, b'no daemon', b'')
            with self.assertRaisesRegex(ValueError, 'No daemon status marker'): session.run('id -u')


class FakeSession:
    def __init__(self, case, fail_preferences=False):
        self.files = {device_ops.DB: (case / 'source.db').read_bytes(),
                      device_ops.PREFS: (case / 'source.xml').read_bytes()}
        self.paused = False; self.killed = False; self.fail_preferences = fail_preferences

    def run(self, command):
        output = b''
        for line in command.splitlines():
            parts = shlex.split(line)
            if not parts: continue
            if parts[0] == 'pidof': output = b'123\n'
            elif parts[:2] == ['kill', '-STOP']: self.paused = True
            elif parts[:2] == ['kill', '-CONT']: self.paused = False
            elif parts[:2] == ['kill', '-KILL']: self.paused = False; self.killed = True
            elif parts[0] == 'sha256sum':
                output = ''.join(burton.sha(self.files[p]) + '  ' + p + '\n' for p in parts[1:]).encode()
            elif parts[0] == 'cat':
                source, target = parts[1], parts[3]
                if self.fail_preferences and source.endswith('/preferences.xml'):
                    self.fail_preferences = False
                    raise ValueError('Simulated second write failure')
                self.files[target] = self.files[source]
            elif parts[0] not in ('test', 'sync'):
                raise AssertionError('Unexpected fake command: ' + line)
        return output


class FakeAdb:
    executable = 'NO_REAL_ADB'
    device = 'DEVICE_PLACEHOLDER'
    def shell(self, command): return ''


class ApplyFailureTests(unittest.TestCase):
    def run_apply(self, case, session):
        def fake_push(args, **kwargs):
            source, directory = Path(args[-2]), args[-1]
            session.files[directory + source.name] = source.read_bytes()
            return subprocess.CompletedProcess(args, 0, b'', b'')
        with mock.patch('device_ops.subprocess.run', side_effect=fake_push):
            device_ops.apply(case, session, FakeAdb())

    def test_partial_write_failure_restores_both_files_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', True)
            session = FakeSession(path, fail_preferences=True)
            with self.assertRaisesRegex(ValueError, 'second write failure'): self.run_apply(path, session)
            self.assertEqual(session.files[device_ops.DB], (path / 'source.db').read_bytes())
            self.assertEqual(session.files[device_ops.PREFS], (path / 'source.xml').read_bytes())
            self.assertFalse(session.paused)
            self.assertFalse((path / 'applied.json').exists())

    def test_stale_device_hash_prevents_any_write_and_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', True)
            session = FakeSession(path); session.files[device_ops.PREFS] = b'new owner settings'
            with self.assertRaisesRegex(ValueError, 'Device files changed'): self.run_apply(path, session)
            self.assertEqual(session.files[device_ops.PREFS], b'new owner settings')
            self.assertEqual(session.files[device_ops.DB], (path / 'source.db').read_bytes())
            self.assertFalse(session.paused); self.assertFalse(session.killed)

    def test_success_keeps_prepared_files_and_restarts_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', True)
            session = FakeSession(path); self.run_apply(path, session)
            self.assertEqual(session.files[device_ops.DB], (path / 'prepared/configuration.db').read_bytes())
            self.assertTrue(session.killed); self.assertFalse(session.paused)
            self.assertTrue((path / 'applied.json').exists())

    def test_stop_delivered_but_response_lost_still_resumes(self):
        class LostStopResponse(FakeSession):
            def run(self, command):
                result = super().run(command)
                if command.startswith('kill -STOP'):
                    raise subprocess.TimeoutExpired('simulated transport', 45)
                return result
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); database = make_case(path)
            burton.prepare(database, path / 'source.xml', 'TEST_TYPE', 'TEST_SERIAL', '2099-12-31', path / 'prepared', True)
            session = LostStopResponse(path)
            with self.assertRaises(subprocess.TimeoutExpired): self.run_apply(path, session)
            self.assertFalse(session.paused)
            self.assertFalse(session.killed)
            self.assertEqual(session.files[device_ops.DB], (path / 'source.db').read_bytes())


class RecoveryGuardTests(unittest.TestCase):
    def test_capture_lost_stop_response_resumes(self):
        class LostStopResponse:
            paused = False
            def run(self, command):
                if command.startswith('pidof'): return b'123\n'
                if command.startswith('kill -STOP'):
                    self.paused = True
                    raise ValueError('No daemon status marker')
                if command.startswith('kill -CONT'): self.paused = False
                return b''
        with tempfile.TemporaryDirectory() as temp:
            session = LostStopResponse()
            with self.assertRaisesRegex(ValueError, 'No daemon status marker'):
                device_ops.capture(Path(temp), session)
            self.assertFalse(session.paused)

    def test_changed_launcher_blocks_capture_but_not_system_recovery(self):
        current = dict(burton.TARGET, device_id_sha256='SYNTHETIC_ID')
        baseline = dict(current, supported=True, uid='2000', selinux='Enforcing')
        current['launcher_version_code'] = 'UNREVIEWED_VERSION'
        adb = mock.Mock(); adb.inspect.return_value = current
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp); (case / 'before-system.json').write_text(json.dumps(baseline))
            with self.assertRaisesRegex(ValueError, 'launcher_version_code'):
                device_ops.state_for_case(case, adb)
            self.assertEqual(device_ops.state_for_case(case, adb, require_launcher=False), baseline)

    def test_failed_reboot_does_not_remove_recovery_transport_first(self):
        class RebootFailure:
            helper = '/data/local/tmp/helper'
            def __init__(self): self.commands = []
            def run(self, command):
                self.commands.append(command)
                if '/system/bin/reboot' in command:
                    raise ValueError('Remote command failed: reboot rejected')
                return b''
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp); (case / 'root-session.log').write_text('synthetic log')
            session = RebootFailure()
            with mock.patch('device_ops.restore_system'), self.assertRaisesRegex(ValueError, 'reboot rejected'):
                device_ops.finish(case, session, FakeAdb())
            for command in session.commands[:-1]:
                self.assertNotIn('kara-root.sock', command)
                self.assertNotIn(session.helper, command)
            final = session.commands[-1]
            self.assertLess(final.index('/system/bin/reboot'), final.index('rm -f'))

    def test_reboot_disconnect_is_reported_unverified(self):
        from root_session import TransportStatusUnknown
        session = mock.Mock(helper='/data/local/tmp/helper')
        session.run.side_effect = [b'', TransportStatusUnknown('shutdown interrupted status')]
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp); (case / 'root-session.log').write_text('synthetic log')
            with mock.patch('device_ops.restore_system'):
                self.assertFalse(device_ops.finish(case, session, FakeAdb()))


if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""Transport for an ALREADY RUNNING authorized temporary daemon. Never obtains root.

Use from the runbook. Calls preserve remote shell quoting and propagate the remote
command's exit code, which the upstream daemon client does not otherwise expose.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys

from burton import Adb, ORIGINAL_HASH, PATCHED_HASH, TARGET, require


class TransportStatusUnknown(ValueError):
    pass


class RootSession:
    def __init__(self, device, helper, adb='adb', verify=True):
        require(bool(re.fullmatch(r'/data/local/tmp/[A-Za-z0-9_.-]+', helper)),
                'Use the exact reviewed helper under /data/local/tmp')
        self.device, self.helper, self.adb = device, helper, adb
        if verify:
            transport = Adb(device, adb)
            digest = transport.shell('sha256sum ' + shlex.quote(helper)).split()[0]
            require(digest in (ORIGINAL_HASH, PATCHED_HASH), 'Unexpected helper hash')
            for key, command in [('device', 'getprop ro.product.device'),
                                 ('model', 'getprop ro.product.model'),
                                 ('build', 'getprop ro.build.version.incremental')]:
                require(transport.shell(command) == TARGET[key], 'Device profile mismatch: ' + key)
            require(self.run('id -u').strip() == b'0', 'No working UID 0 daemon; do not rerun live automatically')

    def run(self, command):
        marker = '__BURTON_STATUS_' + secrets.token_hex(12) + '__'
        wrapped = '( set -e\n' + command + '\n)\nburton_rc=$?\nprintf "\\n' + marker + '%s\\n" "$burton_rc"'
        remote = shlex.quote(self.helper) + ' --cmd ' + shlex.quote(wrapped)
        result = subprocess.run([self.adb, '-s', self.device, 'shell', remote],
                                capture_output=True, timeout=45, check=True)
        payload, separator, status = result.stdout.rpartition(('\n' + marker).encode())
        if not separator:
            raise TransportStatusUnknown('No daemon status marker; inspect state before continuing')
        require(status.strip() == b'0', 'Remote command failed: ' + status.decode(errors='replace').strip()
                + '\n' + payload.decode(errors='replace'))
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--command-file', required=True, type=Path,
                        help='Reviewed remote shell program; no local shell evaluation')
    parser.add_argument('--output', type=Path, help='New private output file; useful for binary backups')
    args = parser.parse_args()
    try:
        session = RootSession(args.device, args.helper, args.adb)
        data = session.run(args.command_file.read_text())
        if args.output:
            with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(data)
        else:
            sys.stdout.buffer.write(data)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('STOP:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

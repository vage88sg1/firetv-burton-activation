# Fire TV Burton Activation — Official Amazon Home UI

[Italiano / full README](README.md) · [Compatibility](skills/firetv-burton/references/compatibility.md) · [Operator workflow](skills/firetv-burton/references/workflow.md) · [Recovery](skills/firetv-burton/references/recovery.md)

Activate the dormant **official Amazon Fire TV Burton interface** inside the
stock signed launcher. Includes a portable **Claude Code / Codex Agent Skill**,
offline configuration tools, an assisted ADB workflow, backups and rollback.
This project does not replace Home with a third-party launcher.

**Verified hardware:** one Fire TV Stick 4K Max first generation, **AFTKA/kara**,
Fire OS **7.7.1.3 PS7713/5443**, incremental build `0035334210436`, stock launcher
**7280112.1**. The redesigned Home worked and survived reboot. Other devices and
firmware are unverified; the live path must stop on a mismatch.

Private configuration access requires an explicitly authorized **temporary-root
kernel attempt**, which can hang or reboot the device. The repository does not
ship an exploit binary, Amazon APKs or firmware. It references a pinned upstream
release and provides a hash-checked one-byte scan-data patch. The packaged tools
have offline tests; they are not a separately qualified automatic hardware installer.

## Use with an agent

```sh
git clone https://github.com/vage88sg1/firetv-burton-activation.git
cd firetv-burton-activation
```

Ask Claude Code or Codex to read `AGENTS.md` and `skills/firetv-burton/SKILL.md`,
inspect your explicitly selected ADB device read-only, verify the exact profile,
agree on expiry and optional refresh freezing, then follow the operator workflow.
The agent needs local access to the TV's network. No API key or project-specific
MCP server is required. Each live root retry requires renewed informed authorization.

For reusable installation, copy `skills/firetv-burton` to
`~/.agents/skills/firetv-burton` for Codex or
`~/.claude/skills/firetv-burton` for Claude Code, preserving an existing skill if
one is already installed. Invoke `$firetv-burton` or `/firetv-burton` respectively.
See the [official Codex](https://developers.openai.com/codex/skills/) and
[Claude Code](https://code.claude.com/docs/en/skills) documentation.

## Read-only check

```sh
adb connect TV_IP:5555
python3 skills/firetv-burton/scripts/burton.py inspect --device TV_IP:5555
```

Then follow the [complete workflow](skills/firetv-burton/references/workflow.md).
It covers the exact compatibility gate, authorization, one root attempt, backup,
offline eligibility/T1 transformation, verification, restoration of helper OTA
side effects, cleanup and final reboot. Nothing in CI connects to a Fire TV.

## Persistence limits

An explicit future expiry such as **31 December 2099** can be selected. An optional
sync-date change suspends normal refresh of the **whole Home configuration bundle**,
not just Burton fields. Future firmware, a launcher update or app-data reset can
remove this protection. Firmware OTA is not blocked by this workflow.

Keep all real device data in ignored `.local/` directories. Never publish a
serial, private network address, original configuration, raw log or backup.

## Check the tools

Requires Python 3.9+ and, for device work, Android Platform Tools.

```sh
python3 -m unittest discover -s tests -v
python3 tools/check_repository.py
```

See [provenance](skills/firetv-burton/references/compatibility.md#provenance),
[third-party notices](THIRD_PARTY_NOTICES.md) and [MIT license](LICENSE).
Independent project; not affiliated with Amazon, Anthropic or OpenAI.

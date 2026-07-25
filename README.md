# HashSight

Hash signature intelligence with terminal-first ergonomics.

```
   _   _           _      ____  _       _     _
  | | | | __ _ ___| |__  / ___|(_) __ _| |__ | |_
  | |_| |/ _` / __| '_ \ \___ \| |/ _` | '_ \| __|
  |  _  | (_| \__ \ | | | ___) | | (_| | | | | |_
  |_| |_|\__,_|___/_| |_| |____/|_|\__, |_| |_|\__|
                                    |___/

                hash signature intelligence
```

HashSight identifies which [hashcat](https://hashcat.net/hashcat/) mode(s) a hash string
belongs to without cracking anything.

## Why HashSight

Identifying a hash format from shape alone is genuinely ambiguous in many cases (for example, a
bare 32-hex value may represent multiple valid families). HashSight is designed around that
reality:

- **Data, not code.** Signatures live in [hashsight/data/signatures.json](hashsight/data/signatures.json).
- **Sourced from hashcat.** Entries are derived from hashcat example hashes.
- **Transparent ambiguity.** Multiple valid candidates are shown and ranked.
- **Fast dispatch.** Prefix bucket -> regex list -> hex-length lookup.
- **Community-maintained.** Contributions go through JSON + tests.

## Install

Requires Python 3.11+.

Quick start (recommended)

```bash
git clone https://github.com/azurekid/HashSight.git
cd HashSight
./run-hashsight.sh --help
```

Run a hash immediately:

```bash
./run-hashsight.sh hash '$6$rounds=5000$abc$def...'
```

What this does on first run:

- checks Python version
- runs HashSight directly from source

No virtual environment or pip install is required for this quick path.

Tip: create a shell alias if you want a shorter command:

```bash
alias hashsight='~/HashSight/run-hashsight.sh'
```

Manual install (advanced)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

Quick Linux install (fault-resistant, advanced)

```bash
# Optional: bootstrap Python 3.11 + venv tooling via apt (Debian/Ubuntu)
sudo ./install-linux.sh --with-apt

# Standard local install (no apt)
./install-linux.sh
```

The installer script validates Python version, creates a virtual environment,
installs HashSight in editable mode, refreshes shell command cache, and verifies
that `hashsight` is callable. It also creates a launcher at
`~/.local/bin/hashsight` so you do not need to manually run venv/pip steps.

If `~/.local/bin` is not already on your PATH, add it once:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

If `hashsight` still says "command not found" after install, run it directly once,
then fix PATH permanently:

```bash
~/.local/bin/hashsight --help
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Some shells cache command lookups. If install succeeded but the command is still not
recognized in the same shell session, refresh and retry:

```bash
# bash/sh
hash -r

# zsh
rehash

hashsight --help
```

```bash
git clone https://github.com/azurekid/HashSight.git
cd HashSight
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

If your tooling expects requirements files:

```bash
python3 -m pip install -r requirements.txt
```

Optional: install shell tab completion support:

```bash
python3 -m pip install '.[completion]'
```

Linux troubleshooting: command not found after install

If `hashsight` is not recognized after install, the package usually did not finish
installing, it was installed into a different Python environment, or Python is
below the minimum supported version.

Use this exact sequence inside your virtual environment:

```bash
source .venv/bin/activate
python3 --version
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
hash -r
which hashsight
hashsight --help
```

Important notes:

- Do not use `--user` inside an active virtual environment.
- `pip install -r requirements.txt` currently points to `-e .`, so it should
   produce the same result as `pip install -e .`.
- HashSight requires Python >= 3.11.
- If entrypoint creation still fails, run `python3 -m hashsight.cli --help` to
   confirm the package imports, then compare `python3 -m pip --version` and
   `which python3` to ensure pip and python are from the same environment.

## Usage

### Command line

```bash
hashsight hash '$6$rounds=5000$abc$def...'
hashsight --hash '$6$rounds=5000$abc$def...'

# `hash` is optional for direct hash input
hashsight '$6$rounds=5000$abc$def...'

# file input also works without `hash`
hashsight < hashes.txt
hashsight --hash < hashes.txt
```

Global help shows the logo/banner by default:

```bash
hashsight --help
```

Use `--no-banner` to suppress it:

```bash
hashsight --no-banner --help
```

HashSight also checks for newer releases automatically in interactive sessions
(cached once per day). Disable this with `--no-update-check` or the environment
variable `HASHSIGHT_NO_UPDATE_CHECK=1`.

Progress lines are shown during analysis in green terminal text using `-` markers.

Use `--no-progress` to disable status lines:

```bash
hashsight hash --no-progress '<hash>'
```

For long hashes, plain output is compact by default (`prefix...suffix (len=N)`).
Use full hash output when needed:

```bash
hashsight hash --full-hash '<very-long-hash>'
```

Ask for JSON output:

```bash
hashsight hash '<hash>' --json

# Add source context to improve ambiguous ranking confidence
hashsight hash '<hash>' --context 'windows ad'

# Tagged hashcat-style formats are supported, e.g. BLAKE2s-256
hashsight hash '$BLAKE2$2c719b484789ad5f6fc1739012182169b25484af156adc91d4f64f72400e574a'
```

Look up known signatures:

```bash
hashsight signature --mode 1800
hashsight --signature --mode 1800
hashsight signature --category 'Crypto Wallet'
hashsight --signature --category 'Crypto Wallet'
hashsight signature --name 'Keccak-256'

# Completion health check
hashsight completion zsh --check
hashsight --completion zsh --check
```

Signature search output is ranked and includes certainty with these columns:

1. name
2. mode
3. john
4. category
5. certainty

Use `--top` to limit results (default `20`) or `--json` for machine-readable output:

```bash
hashsight signature --name 'Keccak' --top 5
hashsight signature --name 'Keccak-256' --json
```

### Shell tab completion

After installing the optional completion extra, use the built-in completion helper.

1. Check prerequisites:

```bash
hashsight completion zsh --check
```

If the check reports `status=not-ready`, install extras first:

```bash
python3 -m pip install '.[completion]'
```

2. Enable completion for your current shell:

For zsh:

```bash
eval "$(hashsight completion zsh)"
```

For bash:

```bash
eval "$(hashsight completion bash)"
```

The generated zsh snippet includes `bashcompinit` automatically because
argcomplete's completion protocol is bash-flavored.

3. Persist it in your shell profile (`~/.zshrc` or `~/.bashrc`) by appending the
generated snippet output.

Reference snippets (equivalent to `hashsight completion <shell>`):

For zsh:

```bash
autoload -U compinit && compinit
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete hashsight)"
```

For bash:

```bash
eval "$(register-python-argcomplete hashsight)"
```

The `eval` line registers completion immediately in your current shell.

If completion still doesn't trigger, confirm `hashsight` resolves to the same
interpreter/environment where `argcomplete` is installed (`which hashsight`, then
`pip show argcomplete` in that same environment) - a `hashsight` on PATH from a
different venv than the one with `argcomplete` installed will not complete.

## Feedback and PRs

Feedback, bug reports, and pull requests are welcome at:

- https://github.com/azurekid/HashSight/issues
- https://github.com/azurekid/HashSight/pulls

When reporting a detection issue, include:

1. `hashsight --help` output (for version context)
2. the command you ran
3. masked sample hash shape (do not paste sensitive real hashes)
4. expected mode(s) and actual mode(s)


### Table output

The plain output summary table uses this order:

1. name
2. mode
3. John
4. category
5. certainty
6. len
7. hash

### As a Python library

```python
from hashsight import get_hash, get_signature

result = get_hash("$6$rounds=5000$abc$def...")
print(result.confidence, result.mode, result.name, result.john_format)

get_signature(mode=1800)
get_signature(category="Crypto Wallet")
```

## Confidence levels

| Confidence | Meaning |
|---|---|
| `Exact` | The format is unique to a single hashcat mode. |
| `Exact (unverified mode #N)` | Format recognized, but the exact mode number may drift between hashcat releases. |
| `Ambiguous` | The format is valid for multiple hashcat modes; candidates are ranked by popularity. |
| `Unknown` | No signature matched. |
| `Invalid` | Empty input. |

## Project layout

```
HashSight/
├── pyproject.toml               # packaging + `hashsight` CLI entry point
├── hashsight/
│   ├── __init__.py              # public API: get_hash(), get_signature()
│   ├── cli.py                   # command-line interface
│   ├── banner.py                # logo/banner rendering
│   ├── matcher.py               # three-tier matching engine
│   ├── signatures.py            # loading/filtering signatures.json
│   ├── assets/
│   │   └── logo.txt             # banner logo asset loaded at runtime
│   └── data/
│       ├── signatures.json      # signature database
│       └── schema.json
├── tests/
│   └── test_hashsight.py        # pytest suite
└── .github/workflows/validate.yml
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT

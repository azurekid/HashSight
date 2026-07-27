```
   _   _           _      ____  _       _     _
  | | | | __ _ ___| |__  / ___|(_) __ _| |__ | |_
  | |_| |/ _` / __| '_ \ \___ \| |/ _` | '_ \| __|
  |  _  | (_| \__ \ | | | ___) | | (_| | | | | |_
  |_| |_|\__,_|___/_| |_||____/|_|\__, |_| |_|\__|
                                   |__/
                                         (v2.0.1)

           hash signature intelligence
```

# HashSight

Hash signature intelligence for hashcat mode identification.

## Install

Requires Python 3.9+.

```bash
git clone https://github.com/azurekid/HashSight.git
cd HashSight
python3 -m pip install --user .
export PATH="$(python3 -m site --user-base)/bin:$PATH"
hash -r
hashsight --help
```

For the shorter alias, use `hs --help`. If your system already has Hammerspoon installed, `hs` may already be taken there, so `hashsight` remains the safer fallback.

If `hashsight` is not found, run once as a module:

```bash
python3 -m hashsight --help
```

Then persist PATH:

```bash
echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Usage

```bash
hashsight hash '<hash>'
hashsight --hash '<hash>'
hashsight signature --name 'Keccak'
hashsight --version
hs --hash '<hash>'
```

Notes:
- Running just `hashsight` now shows help.
- `hs` is available as a shorter alias when the package is installed, but it can collide with Hammerspoon on macOS.
- Hash input can be piped: `hashsight --hash < hashes.txt`.
- Use `--json` for machine-readable output.

## Troubleshooting

`error: externally-managed-environment` (Debian/Ubuntu/Kali):

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
hashsight --help
```

If completion is needed:

```bash
python3 -m pip install '.[completion]'
```

## Feedback

- Issues: https://github.com/azurekid/HashSight/issues
- Pull requests: https://github.com/azurekid/HashSight/pulls

## License

MIT

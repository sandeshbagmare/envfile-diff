# envfile-diff

Compare two `.env` files by key — with the secret values masked.

[![PyPI](https://img.shields.io/pypi/v/envfile-diff.svg)](https://pypi.org/project/envfile-diff/)
[![Python](https://img.shields.io/pypi/pyversions/envfile-diff.svg)](https://pypi.org/project/envfile-diff/)
[![tests](https://github.com/sandeshbagmare/envfile-diff/actions/workflows/ci.yml/badge.svg)](https://github.com/sandeshbagmare/envfile-diff/actions/workflows/ci.yml)
[![license](https://img.shields.io/pypi/l/envfile-diff.svg)](https://github.com/sandeshbagmare/envfile-diff/blob/main/LICENSE)

```console
$ envfile-diff .env.staging .env.production
+ NEW_RELIC_KEY=***
- LEGACY_TOKEN=***
~ DATABASE_URL=*** (changed)
1 added, 1 removed, 1 changed
```

`diff .env.staging .env.production` prints your production passwords into the
terminal, the transcript and the CI log. This prints the keys and masks the values,
so a review conversation can happen without a secrets leak. Add `--show-values` when
you are on your own machine and actually need them.

## Install

```console
pip install envfile-diff
```

## Use

```console
envfile-diff old.env new.env                  # masked
envfile-diff old.env new.env --show-values    # the real values
envfile-diff old.env new.env --json           # {"added": [...], "removed": [...], ...}
envfile-diff old.env new.env --exit-code      # CI gate: exit 1 when they differ
```

```python
from envfile_diff import diff_env, diff_files, parse_env, render

diff = diff_files(".env.staging", ".env.production")
diff.is_empty
diff.added, diff.removed, diff.changed, diff.unchanged
for change in diff.changes():          # sorted by key
    print(change.key, change.kind)     # "added", "removed" or "changed"
print(render(diff, show_values=False))
```

## What the parser understands

- comments and blank lines, `export KEY=value`
- `KEY=` (empty), spaces around `=`
- `"double quoted"` values with `\n`, `\t`, `\r`, `\"`, `\\` escapes
- `'single quoted'` values, taken literally, `#` inside any quotes
- a trailing `# comment` after an unquoted value
- CRLF files, keys with dots or dashes (`DB.HOST`, `MY-KEY`)
- a repeated key keeps the last value, as a shell does

A line that is not an assignment raises `EnvParseError` with the line number instead
of being silently dropped — a typo in a `.env` file is exactly the kind of thing you
want to hear about.

## Values never leak by accident

Masking is the default in the function (`render(show_values=False)`), in the CLI and in
`--json`. Even with `--json` the payload holds key names only; `--json --show-values`
is the one combination that prints values.

## Development

```console
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

## License

MIT.

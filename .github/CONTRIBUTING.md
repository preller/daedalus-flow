# Contributing

## Setup

daedalus-flow uses [uv](https://docs.astral.sh/uv/) and needs Python 3.12 or
newer. The recipes run through [just](https://github.com/casey/just), a system
binary (`nix profile install nixpkgs#just` or `cargo install just`).

```sh
uv sync --locked --all-groups
```

A plain `uv sync` leaves `just typecheck` and `just test` failing at import,
because the scientific stack sits behind dependency groups.
`uv run pre-commit install` adds the commit-time hooks, which run the fast part
of the gate.

Nix users can copy `.envrc.defaults` to `.envrc` and run `direnv allow`; direnv
then loads the flake dev shell on entry.

## Gate

Run `just gate` before you open a pull request. It runs lint (ruff check and format), typecheck (mypy), imports (the
import-layer contracts), test (the fast suite under the coverage floor), and audit. `just test` skips the real samplers and `just test-slow` runs them;
`just --list` shows the other tiers.

## Code style

- ruff is pinned to `0.15.16` in the pre-commit hook, `just lint` and CI; let it decide formatting.
- mypy runs in strict mode.
- Write in American English and follow the conventions of the file you are editing.

## Pull requests

- One change per pull request, with a test.
- Say what the change does and why, and link the issue if there is one.
- Open an issue first for a new dependency or a change to a public contract: a CLI command, a `lab.yaml` field, the `--json` envelope or an outcome code.

## Generated code

Tools that write code are welcome. Name the tool in the pull request and take
responsibility for every line. Do not submit generated code you have not read.

## Security

Report a vulnerability privately as described in `SECURITY.md`, not in a public issue.

# AGENTS.md

Notes for coding agents working in this repository. Read
`.github/CONTRIBUTING.md` first; the list below is the short form.

- Set up with `uv sync --locked --all-groups`; every `just` recipe runs through `uv run`.
- Run `just gate` before a pull request: lint, typecheck, imports, test and audit.
- Do not change the bundled labs under `src/daedalus/examples/**`; the tests treat them as goldens.
- Say in the pull request which agent or tool wrote or changed the code.

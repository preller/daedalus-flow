# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- The `dae` CLI: scaffold examples (`dae example`), design and inspect labs
  (`dae lab init`, `dae lab validate`, `dae lab visualize`), run them
  (`dae lab run`), and follow flows (`dae flow status`, `dae flow resume`).
- Module workbench: `dae module create`, `dae module try`,
  `dae module validate`, and `dae module convert` to bring an existing script
  into a lab.
- A machine-readable `--json` envelope on every command, with a stable
  outcome-code contract (see `docs/reference/outcome-codes.md`).
- Local engine with per-module environment isolation (ambient, uv, or nix)
  and opt-in parallelism; optional Prefect backend via the `engine` extra.
- A bundled example ladder, from `minimal` to the full `demo` reference lab.

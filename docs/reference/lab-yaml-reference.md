# The lab.yaml manifest

A lab is a recipe. `lab.yaml` lists the modules to run and how they depend on
each other; daedalus works out the run order and executes each module. Input is
read from the lab's `input/` folder by default.

```yaml
name: ensemble

modules:
  - id: emit
  - id: analyze
    depends: [emit]
  - id: collect
    depends: [analyze]
```

## Optional top-level fields

A minimal `lab.yaml` needs only `name` and `modules`.

### `max_workers`

How many steps may run at once. A positive integer; the default is `1`.

- `max_workers: 1` (the default) runs every step in-process, one at a time, in
  one deterministic order.
- `max_workers: N` (`N` greater than `1`) runs independent branches in parallel
  on the local engine. Ready steps dispatch in waves of at most `N`, each step
  in its own `uv`-provisioned subprocess, so every module must declare its
  imports in its `requirements.txt`. The result is identical to a serial run;
  only the wall-clock time changes.

`max_workers` must be 1 or more; any other value is an error.

### `engine`

The orchestration backend. A known engine name; the default is `local`.

- `local` is the built-in in-process engine. It is always available.
- `prefect` is the optional backend behind the `engine` extra
  (`pip install "daedalus-flow[engine]"`). The same recipe runs unchanged on
  either engine; Prefect adds a live run dashboard. An unknown engine name is
  an error.

### `isolation`

The lab-wide isolation policy. When omitted, daedalus picks a default from
`max_workers`: `1` runs in-process (`ambient`), and greater than `1` runs each
step in its own `uv`-provisioned environment (`uv`).

- `auto` honors each module's own preference (see "Per-module isolation" below),
  so one lab can mix `uv` and `nix` environments.
- `ambient` runs every step in the active environment, in-process. It is not
  concurrency-safe, so setting it explicitly requires `max_workers: 1`.
- `uv` forces every step into its own `uv`-provisioned environment, built from
  the module's `requirements.txt` (or `uv.lock`).
- `nix` forces every step into a per-module nix environment (a host
  prerequisite; see the `isolation-nix` example). The reproducible contract is a
  committed `flake.nix` (pinned nixpkgs plus a `flake.lock`) beside the module,
  which daedalus builds directly. Each module resolves in this order:

  1. its own `flake.nix`;
  2. else a generated env from its `uv.lock` or `requirements.txt` (a
     dev-convenience path, not the contract);
  3. else a `dae.lab.validate.nothing_to_nixify` error.

`fused` is rejected. An unknown isolation name is an error.

### Per-module isolation (`dae-module.yaml`)

A module declares its own isolation preference in its `dae-module.yaml`, so the
module carries its environment needs; copied into another lab it isolates the
same way:

```yaml
role: transform
isolation: nix            # a single preference
# isolation: [nix, uv]    # OR a priority ladder (strongest first)
# (omitted)               # = none: fuse into the lab environment
```

Values are `none`, `uv`, `nix`, with strength `none < uv < nix`. A ladder lists
acceptable isolations in decreasing strength. Resolution depends on the lab
policy alone, not on what the host can build, so the same lab resolves the same
way on every machine. A `nix` preference needs a `flake.nix`, a `uv.lock`, or a
`requirements.txt` to build from; a `uv` preference needs a `requirements.txt`
or `uv.lock`. A preference without files behind it is a
`dae.lab.validate.isolation_unbacked` error.

The preference is soft. A lab policy never forces a stronger isolation. A
downgrade (the policy runs a module below its top preference) is a validate
warning, not a run failure; a ladder fallback does not warn.
`dae lab validate --json` carries the resolved per-module plan in a
`resolution` block (`strategy`, `downgraded`, `source`, `flake_origin`), and
the human output renders it.

## Relationship to the run output

`dae lab run` and `dae flow status` report the `engine` and `max_workers` a flow
ran under, so a serial run is distinguishable from a parallel one. For why a
run can produce more step instances than the recipe has modules, see
[`recipe-vs-run-counts.md`](../explanation/recipe-vs-run-counts.md).

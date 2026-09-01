# Isolate module dependencies

Two steps in a lab may need conflicting versions of one library, or you may
want each module pinned to its own environment. Per-module isolation builds
each module its own environment from its own lock file.

In the `isolation-nix` example two modules pin different versions of the same
library and both run in one `dae lab run`, each seeing only its own pin.
Scaffold it:

```bash
dae example isolation-nix
cd isolation-nix
```

## The shape

```bash
dae lab visualize
```

The recipe is a diamond. `seed` feeds two render branches and `verify` joins
them back:

```text
seed -> render_classic (pyfiglet==1.0.2) -.
    \-> render_modern  (pyfiglet==1.0.4) --> verify
```

`render_classic` pins the older library version and `render_modern` the newer
one. `verify` is a walk-collector that asserts the two branches ran under
different, correctly pinned versions; one environment leaking into the other
turns the run red.

## The knob: `isolation`

Open `lab.yaml`:

```yaml
isolation: auto
max_workers: 2
```

`auto` honors each module's own `dae-module.yaml` `isolation:` preference, so
one lab can mix environments. The per-module values choose how each module's
environment is built:

- `ambient` builds nothing and runs in the current process; every module shares
  one environment. A serial lab (`max_workers: 1`) runs this way when no module
  states a preference.
- `uv` provisions each module a subprocess environment from its
  `requirements.txt`.
- `nix` builds each module an environment from its own `pyproject.toml` and
  `uv.lock`. The Nix closure carries its own system libraries, so there are no
  `LD_LIBRARY_PATH` shims to manage.

Each module's pins live in its own folder. To adapt this lab, swap `pyfiglet`
for your library, change the pin in each module's `pyproject.toml`, and run
`uv lock` in that module.

## Preview the plan

`--dry-run` shows what a run will do without building anything, on any host:

```bash
dae lab run --dry-run
```

```text
╭──────────────────────────╮
│ plan preview (--dry-run) │
╰──────────────────────────╯
Lab: isolation-nix   whole-lab run plan   (4 modules)
────────────────────────────────────────────────
 #       module           module dir (in lab)
────────────────────────────────────────────────
01   T   seed             modules/seed
02   T   render_classic   modules/render_classic
03   T   render_modern    modules/render_modern
04   W   verify           modules/verify
nothing was written (--dry-run shows the plan only)
these are the recipe's modules; at run time each fanned module expands by its input rows
into more step instances. Run `dae lab run` to materialize them.
Next: dae lab run   (execute the plan for real)
```

## Run it for real

`isolation: nix` needs a build-capable Nix with flakes enabled (a multi-user
daemon with a writable store, or a host whose kernel allows Nix's sandbox). When
that is available:

```bash
dae lab run
```

Without a usable Nix the run stops with `dae.lab.run.isolation_unavailable`
instead of using a shared environment; `--dry-run` shows the plan on any host.

```text
dae.lab.run.isolation_unavailable   (exit 1)
```

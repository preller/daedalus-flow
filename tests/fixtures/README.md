# Fixtures

Test fixtures for daedalus, kept out of the example gallery (`minimal`, `demo`).

- `labs/` - self-contained lab fixtures. Each has its own `lab.yaml`, `input/`
  and `modules/`, so it validates and runs on its own. `labs/exoplanet_validation/`
  is the end-to-end pipeline; `labs/diamond_join/` is a join where one module
  depends on two parents.
- `modules/` - one module fixture per role: `emit_pair` (emitter),
  `scale_series` (transform), `merge_walks` (walk_collector) and
  `reduce_flights` (flight_collector). Each carries its own input, a golden
  `expected/`, and a `requirements.txt` with a distinct numpy pin.
- `broken_labs/` - invalid `lab.yaml` specs (cyclic, dangling dependency, two
  emitters). They hold only `lab.yaml` and each module's `dae-module.yaml`;
  validation is topology-only and stops before any module body is read.
- `broken_modules/` - invalid module fixtures (missing `@dae.entry`, unknown
  role, name mismatch) for the per-module validator.

## Shape fixture modules

Shape fixture modules (`labs/*/modules/*/main.py`) share one body: they assert
directory layout and walk strings, not science. Each writes a marker with the
derived seed, step id and walk id so rerun and identity assertions have a
stable artifact.

The `complex` lab (and its copy under `src/daedalus/examples/complex`)
exercises every legal walk-model shape: nested branch/collect levels, sibling
collectors, a single-input collector, asymmetric branches, and an
emitter/flight_collector frame. Every module is a pass-through that records its
coordinates and the path of module ids above it.

## Other lab fixtures

- `linear_smoke` - a strictly linear chain, emitter to flight_collector; the
  engine smoke test, stdlib only.
- `brancher_nested` / `brancher_mixed` - role-only fixtures for the brancher
  predicate; no module body ever runs.
- `emitter_range0` / `emitter_range1` / `emitter_range5` / `emitter_list_abc` -
  dynamic flights, M = len(`input/items.json`); the test reads the same file.
- `flight_one_fails` - the emitter_range5 shape where `work` raises on one
  flight's item.
- `flight_final_merge` / `flight_final_merge_m2` - three sibling walk_collectors
  feeding one flight_collector; the per-flight `final/` must hold all three files.
- `nix_diamond` / `science_nix` - per-module `isolation: nix` envs built by
  uv2nix from each module's own lock.

## Walk-shape suite

`tests/core/test_walk_shapes.py` drives the suite over the fixtures below. The
assertions are about shape (the `Full:` / `Walks:` block, the nested
`walks/walk_J/` copy tree, and the exact validate codes), not science. Module
names are chosen so `lexicographical_topological_sort(key=str)` assigns
deterministic node numbers.

Runnable shapes (`labs/`), one row per fixture:

- `chain_plain` - linear chain, the M=1 baseline.
- `wide4_join` / `wide5_join` - brancher x4/x5 into one collector.
- `asym_join` - unbalanced branch lengths; walk_inputs map to tails.
- `nested_join` - nested branchers, per-level collectors.
- `series_diamonds` - a diamond feeding a diamond; the walk counts add.
- `repeat_then_collect` - repeated transform then a collector.
- `diamond_repeat` - repeated terminal, both branches uncollected.
- `wide4_repeat` / `wide5_repeat` - wide brancher, repeated terminal.
- `mixed_collect` - inner group collected, outer group uncollected.
- `sibling_collectors` - the exoplanet shape at M=1: emitter, brancher x4,
  three same-group sibling collectors, flight_collector, sink.

Plus `diamond_join`, `exoplanet_validation`, and the example gallery's `demo`.

Must-refuse shapes (`broken_labs/`), each asserting its exact
`dae.lab.validate.<token>` and the `dae.lab.run.invalid` refusal:

- `partial_group`, `cross_brancher_merge`, `cross_level_merge` ->
  `collector_incomplete_group`.
- `collector_no_walks` - the reconverge shape -> `collector_no_walks`.
- `walks_reach_fc` -> `walks_reach_flight_collector`.
- `emitter_fanout` -> `emitter_multi_successor`.
- `budget_blowup` - 11 nested branchers -> `walk_budget_exceeded`.
- `bad_module_id` - an id with `@` -> `reserved_separator_in_id`.

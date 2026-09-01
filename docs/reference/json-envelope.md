# The `--json` envelope

Every `--json` command writes one object with four keys: `code`, `exit`,
`error`, `data`. `--json` may appear anywhere in argv; `dae --json lab
visualize` and `dae lab visualize --json` emit the same object. The terminal
output is a render of the same data.

```jsonc
{
  "code": "dae.<group>.<command>.<result>",  // the stable dotted outcome code
  "exit": 0,                                   // the process exit status
  "error": null,                               // the failure cause, or null
  "data": { }                                  // the per-command payload, or null
}
```

- `code` is the stable outcome code (see [outcome-codes.md](outcome-codes.md)).
- `exit` is the process exit status the code's category carries.
- `error` is `null` on success and a cause object on failure.
- `data` holds the per-command payload, or `null` when a command has none.

A command never spreads its payload at the top level; it nests it under `data`.

## The `error` cause object

On a failed run the `error` slot carries the cause read from the first failed
step:

```jsonc
{
  "error": "step 'work' raised ValueError: doomed item 20",  // the message
  "reason": "step 'work' raised ValueError: doomed item 20",  // alias of error
  "code": "dae.step.execution_failed",  // how the step failed (see below)
  "module": "work@w2",                   // the failed step-instance id
  "missing_dep": "numpy"   // present only for an absent third-party import
}
```

`code` is the failed step's `dae.step.*` taxonomy code, a per-step identity
distinct from the run-level `code` on the envelope. It is one of:

- `dae.step.load_failed` - the module never ran (a top-level import error, a
  missing `@dae.entry`, or a native-lib dlopen failure).
- `dae.step.execution_failed` - the module loaded then raised while running.
- `dae.step.worker_failed` - the worker process died around the module (a signal
  kill, a bare broken pipe with no module traceback, or an out-of-memory kill).

All three carry the `FAILURE` category (exit 1). The run-level code
(`dae.lab.run.failed` / `missing_deps`) is unchanged; the two layers coexist.
The full traceback is written to a `step-error.log` file beside the failed
step's output; the terminal prints the final frame and the path to that file.

`flow status` exits 0 even for a failed flow, so its envelope can carry a
non-null `error` with `exit: 0`. The cause describes the reported flow, not the
status command.

`dae lab validate --deep` reuses the same two layers before any run. It builds
every module's isolation closure and imports each module's entry without
running it. A closure that will not build, or an entry that will not import, is
a load-time failure. The envelope `code` stays a validate verdict
(`dae.lab.validate.isolation_unbacked`); the `error` slot carries
`code: dae.step.load_failed` naming the module. Plain `dae lab validate` never
builds; it points at `--deep` when modules resolve to a closure backend.

## The `data` payload per command

`data` is `null` unless a command produces a payload. The producing commands:

| command | `data` shape |
| --- | --- |
| `example` (list) | `{"examples": [{"name", "available", "description"}, ...]}` |
| `example <name>` | `{"paths": [...]}` |
| `lab init <name>` | `{"paths": [...]}` |
| `lab validate` | `{"recipe": {"modules", "source"?, "sink"?} \| null}` |
| `lab visualize` | `{"topology": {...}, "walks", "walk_lines", "token_walk_lines"}` |
| `lab run --dry-run` | `{"plan": [{"order", "module", "role", "module_dir"}, ...]}` |
| `lab run` | the flow payload (see below) |
| `flow status` | the flow payload (see below) |
| `flow resume` | the flow payload (see below) |
| `module create` | `{"paths": [...]}` |
| `module convert` | `{"paths": [...]}` |

Path-producing commands all use the one `paths` key; `lab clean` reports
removed paths under `paths` too, and the outcome code says which.

`lab validate` always carries `data.recipe` on the ok outcome: the summary
object for a real recipe, or `null` for the no-lab exemplar fallback.

`lab visualize` gives one shape for the one outcome code `dae.lab.visualize.ok`
whether or not a `./lab.yaml` exists. The no-lab exemplar view computes no walk
census, so its `walks` / `walk_lines` / `token_walk_lines` are present but
null; a real cwd lab fills them. Each `topology.nodes` entry carries
`{id, role, layer, flight_scoped}`. `flight_scoped` is true for a module inside
the per-flight band, a descendant of an emitter and an ancestor of a
flight_collector.

`lab visualize --style {table,full,num,rolenum}` selects the human render only.
The `--json` payload is identical across every style. The graph views need the
`viz` extra (grandalf); without it the human command prints an install hint
instead of a graph, and the `--json` payload is unaffected.

### The flow payload

`lab run`, `flow status`, and `flow resume` share one builder, so they emit the
same `data` shape:

```jsonc
{
  "flow_id": "flow_20260618_120000",
  "lab_name": "linear_smoke",
  "status": "completed",                 // or "failed"
  "created_at": "2026-06-18T12:00:00+00:00",
  "engine": "local",                     // orchestration backend
  "max_workers": 1,                      // concurrency degree (serial == 1)
  "steps": [ {"id", "status", "duration_s", "started_at", "finished_at", "error", "error_code"} ],
  "walks": [ {"walk_id", "flight_id", "parent_walk", "born_at", "branch_module", "user_walk"} ]
}
```

The failure cause is not inside this payload; on a failed run it rides the
envelope `error` slot. A failed step also carries `error` and `error_code` on
its `steps` row; a successful step row omits them.

## Meta-flags sit outside the envelope

`--help`, `--version` (`-V`), and the completion installers
(`--install-completion`, `--show-completion`) are eager meta-flags: they print
and exit 0 before any command runs, so they do not route through the envelope
and own no `dae.*` outcome code. `dae --version` prints one line
(`dae <version>`) even under `--json`, as `--help` does.

## Limitation: Typer usage errors are not JSON

A Typer/Click-level usage error (an unknown option, or a missing or extra
argument) is reported as raw text on stderr with exit status 2, not as a
`--json` envelope. Click rejects it during parsing, before any callback runs.
For example, `dae lab run --bogus` exits 2 with a "No such option" message on
stderr and writes nothing to stdout.

# Your first lab

This page scaffolds the `minimal` lab, runs it, and reads the result. Install
first ([install](install.md)). `minimal` is stdlib-only, so a plain install is
enough.

## 1. Scaffold the smallest lab

A *lab* is a folder with a recipe (`lab.yaml`) and the modules it runs.
`daedalus-flow` ships a ladder of ready-made examples; `minimal` is the
smallest one that runs. Scaffold it:

```bash
dae example minimal
```

```text
scaffolded example 'minimal' into ./minimal/
edit minimal/input/raw.csv with your own input data, then run the lab.
Next: cd minimal && dae lab validate && dae lab visualize && dae lab run --dry-run
```

That `Next:` line is `dae` pointing you at the next step. The tool does this
after most commands, so if you lose your place, read the last line it printed.
Move into the new folder:

```bash
cd minimal
```

## 2. Look inside

The scaffold created:

```text
input/raw.csv          # the data the lab reads
lab.yaml               # the recipe: which modules run, and in what order
modules/normalize/     # the one module, with its code and a tiny expected-output check
tutorial.ipynb         # this walkthrough as a runnable notebook
tutorial.py            # the same notebook as a plain script; you need neither today
```

Open `lab.yaml` to see the whole recipe:

```yaml
name: minimal

modules:
  - id: normalize
```

One module, named `normalize`. The recipe does not say how to run it or in what
order; `daedalus-flow` works that out, which matters more as labs grow.

## 3. Validate the recipe

Check that the recipe is sound before you run it:

```bash
dae lab validate
```

```text
Lab recipe at /.../minimal/lab.yaml is sound.
```

`validate` reads the recipe and the module declarations and checks that every
dependency exists, that there are no cycles, and that the shape is runnable. It
does not execute anything. If you mistype a module id in your own labs, this
command reports it, with an exit code a script can check.

## 4. See the shape

Now picture the lab before you run it:

```bash
dae lab visualize
```

```text
Lab: minimal   (1 module)
 #       layer   node        feeds-into
01   T       0   normalize   -  (sink)
legend:  E emitter   T transform   W walk-collector   F flight-collector
source: normalize   sink: normalize
```

`visualize` prints the recipe as a table with one row per module, its role
(here `T` for transform), and what it feeds into. With one module, `normalize`
is both the source and the sink. In a larger lab this view is how you confirm
the wiring matches what you intended before spending time on a run.

## 5. Run it

Now run the lab:

```bash
dae lab run
```

```text
Flow: flow_20260621_170646   completed   (1 step instance)
  1/1 step instances completed
  results: /.../minimal/dae-outputs/flows/flow_20260621_170646/final
  lineage: /.../minimal/dae-outputs/flows/flow_20260621_170646
```

The run got a *flow* id (a timestamped name), so no run overwrites a previous
result. It printed a `results:` path for the final output and a `lineage:` path
for the provenance tree, and it `completed`. Your timestamp will differ.

## 6. Read the result

The run printed where the result landed. Read it:

```bash
cat dae-outputs/flows/*/final/normalized.json
```

```json
{
  "time_bjd": [2459000.1, 2459000.2, 2459000.3, 2459000.4, 2459000.5],
  "flux_normalized": [1.0039, 1.0018, 1.0, 0.9988, 0.9975],
  "median_flux": 0.9973,
  "n_points": 5
}
```

The `normalize` module read the raw light curve from `input/raw.csv`, divided by
the median flux, and wrote the normalized series. The result of any step, for
any run, sits at the path the run printed.

`dae flow status` reads the latest run back:

```bash
dae flow status
```

```text
flow_20260621_170646   minimal   completed
 #      step instance    status      time
01      normalize@w1    completed   0.01s
status is read-only; it never changes a flow.
```

## Where to go next

- The [how-to guides](../how-to/index.md) cover fanning one analysis across
  many targets, running branches in parallel, and giving each module its own
  pinned environment.
- [Concepts](../explanation/index.md) explain how a recipe expands into the
  runs you saw.
- The [reference](../reference/index.md) lists every command, field, and
  outcome code.

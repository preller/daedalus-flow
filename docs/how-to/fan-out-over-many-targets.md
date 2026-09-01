# Fan out over many targets

You have one analysis and a list of targets, and you want to run the analysis
once per target and gather the results into one summary. The recipe describes
the analysis once; the engine expands it over the input rows.

The `ensemble` example is the smallest lab that does this. Scaffold it:

```bash
dae example ensemble
cd ensemble
```

## The shape

```bash
dae lab visualize
```

```text
Lab: ensemble   (3 modules)
 #       layer   node      feeds-into
01   E       0   emit      analyze
02   T       1   analyze   collect
03   F       2   collect   -  (sink)
legend:  E emitter   T transform   W walk-collector   F flight-collector
source: emit   sink: collect
```

- `emit` is an emitter (`E`). It reads the target list and starts one *flight*
  per target. A flight is the chain of work for a single target.
- `analyze` is a transform (`T`). It runs once per flight, scoring one target.
- `collect` is a flight-collector (`F`). It waits for every flight to finish,
  then gathers them into one summary.

The recipe lists three modules. The fan-out happens at run time, driven by how
many rows the input has.

## Point it at your targets

The targets live in `input/targets.csv`, one row per target:

```text
name,value,period_days,rp_rstar
...
```

Edit that file to list your own targets; one row becomes one flight. For how
three modules become one run per target plus the collector, read
[recipe vs run counts](../explanation/recipe-vs-run-counts.md).

## Run it

```bash
dae lab run
```

```text
Flow: flow_20260621_170727   completed   (6 step instances)
  6/6 step instances completed
  results: .../ensemble/dae-outputs/flows/flow_20260621_170727/final
```

The recipe had three modules and the run reports six *step instances*: the
emitter ran once, `analyze` ran once per target, and `collect` ran once to
gather them. Add a row to `input/targets.csv` and that count grows by one, with
no change to the recipe. The gathered summary is in the `final/` results folder.

## Scaling up

The engine works out the fan-out and the run order. When running one target at
a time is slow, [run modules in parallel](run-modules-in-parallel.md).

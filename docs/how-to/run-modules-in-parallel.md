# Run modules in parallel

When a lab has branches that do not depend on each other, the engine can run
them at the same time. One field in the recipe turns this on.

The `parallel` example is built for this. Scaffold it:

```bash
dae example parallel
cd parallel
```

## The shape

```bash
dae lab visualize
```

```text
Lab: parallel   (6 modules)
 #       layer   node        feeds-into
01   T       0   split       stat_max, stat_mean, stat_min, stat_sum
02   T       1   stat_max    combine
03   T       1   stat_mean   combine
04   T       1   stat_min    combine
05   T       1   stat_sum    combine
06   W       2   combine     -  (sink)
legend:  E emitter   T transform   W walk-collector   F flight-collector
```

`split` hands the data to four branches (`stat_sum`, `stat_max`, `stat_min`,
`stat_mean`), one statistic each. The four share no dependency, so they can run
concurrently. `combine` is a walk-collector (`W`); it waits for all four
branches to finish, then merges them.

## The knob: `max_workers`

Open `lab.yaml`:

```yaml
engine: local
max_workers: 1
```

`max_workers` is how many steps may run at once. The default, `1`, runs the
branches one at a time and needs no extra setup. To run the four branches side
by side, raise it:

```yaml
max_workers: 4
```

## Run it

```bash
dae lab run
```

```text
Flow: flow_20260621_170728   completed   (6 step instances)
  6/6 step instances completed
```

When the run finishes serially, `dae` prints a reminder:

```text
ran serially on the local engine (max_workers 1): steps ran one at a time.
for concurrency, set max_workers > 1 in lab.yaml or use the prefect engine.
```

## The Prefect engine

The built-in `local` engine runs the ready branches in its own worker pool. The
optional Prefect engine runs the same recipe and adds a live run dashboard.
Install it and switch the backend:

```bash
pip install "daedalus-flow[engine]"
```

```yaml
engine: prefect
max_workers: 4
```

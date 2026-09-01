# Recipe counts vs run counts

The static views (`dae lab visualize` and `dae lab run --dry-run`) count the
modules in the recipe. A real `dae lab run` counts step instances. The two
numbers differ whenever a lab fans out: an emitter turns its input rows into
flights, and every module after it runs once per flight.

## Worked example: the `ensemble` lab

`ensemble` has three modules (`emit` -> `analyze` -> `collect`) and an input
file with four target rows.

`dae lab visualize` shows the static recipe:

```
Lab: ensemble   (3 modules)
...
walks
Full:  1-2-[3]
Walks: 1
  walk_1: 1-2-[3]
```

`dae lab run --dry-run` shows the same recipe as a plan:

```
Lab: ensemble   whole-lab run plan   (3 modules)
```

The real run expands each fanned module by its input rows. `dae lab run`
prints a summary, and `dae flow status` the per-instance table:

```
Flow: flow_...   completed   (6 step instances)
  6/6 step instances completed
  results: .../flows/flow_.../final
  lineage: .../flows/flow_...
```

```
01   emit@w1                  completed
02   analyze@w2  [flight_1]   completed
03   analyze@w3  [flight_2]   completed
04   analyze@w4  [flight_3]   completed
05   analyze@w5  [flight_4]   completed
06   collect@w1               completed
```

The static views counted 3 modules; the run did 6 step instances. The four
input rows turned the single `analyze` module into four step instances, while
`emit` and `collect` each ran once. The static count is what is in the recipe;
the run count is what the recipe expands to once the input is read.

## The `walk_J` / `flight_K` label and the `@wN` token

`dae lab visualize` numbers the user-facing pipelines `walk_1..walk_M`, reset
per flight. The runtime step ids carry a propagation token `@wN` that is offset,
because the root walk is `w1`; the first user pipeline is `@w2`. `dae lab run`
and `dae flow status` print the user-facing label beside the token:

| Lineage shape | Token | Label |
|---|---|---|
| branch walk (a brancher's child pipeline) | `@w2`, `@w3`, ... | `[walk_1]`, `[walk_2]`, ... |
| per-target flight walk (one input row each) | `@w2`, `@w3`, ... | `[flight_1]`, `[flight_2]`, ... |
| root walk | `@w1` | (no label) |

In the `ensemble` table above, `analyze@w2 [flight_1]` is the analyze step for
the first input target. The token is the durable id that the lineage tree and
the `--json` `steps` array expose; the label maps it back to the visualize
vocabulary.

# Concepts

A glossary of the words daedalus uses, with one running example: fitting
transit light curves for a list of target stars. The `dae lab visualize`
output, the run tables and the `--json` payload all use these words.

## The building blocks

**Lab.** A lab is a recipe. It is a folder with a `lab.yaml` that lists the
modules to run and how they depend on each other, plus the modules themselves
and an `input/` folder. daedalus reads the recipe, works out the order, and runs
it. Think of a lab as a single reproducible analysis: "fit every target in my
list and gather the results."

**Module.** A module is one step of the analysis: a small folder with a
`dae-module.yaml` (which declares the module's role) and a `main.py` (which does
the work). A module reads from an input folder and writes to an output folder
that the engine hands it; it never hardcodes a path. One module might read a
target list, another might fit one transit, another might gather all the fits.

**Token.** A token is the label daedalus attaches to a single run of the lab as
it branches, so that every step instance knows which branch it belongs to. When
the analysis fans out, one copy per target or one copy per fitting method, each
copy carries its own token. Downstream steps use it to pick out their own data.
You will see tokens written as `@w1`, `@w2`, and so on in the run tables; `@w1`
is the root that every branch shares, and the branches are numbered from `@w2`.
The token is an internal bookkeeping id, durable across the whole run; the
`[flight_1]` and `[walk_1]` labels beside it (see below) are the names meant
for reading.

**Walk.** A walk is one path through the recipe from the source to the sink: one
specific sequence of modules. A lab with no branches has a single walk. When the
recipe branches (for example, fit each target with both nested sampling and
MCMC), each combination of choices is a separate walk. `dae lab visualize`
numbers them `walk_1`, `walk_2`, and so on.

**Flight.** A flight is one pass through the recipe for one input row. When an
emitter reads a target list of four stars, it starts four flights, and every
module after it runs once per flight. `dae lab run` labels the per-target step
instances `[flight_1]`, `[flight_2]`, and so on, in input-row order.

A **walk** is a branch in the *method*, more than one way to analyze the same
data. A **flight** is a fan-out over the *data*, the same analysis applied to
each target. A lab can do both.

**Source and sink.** The source is the emitter: the one module that starts the
lab by reading your input and producing the first outputs. The sink is the
final collector, the one module that everything funnels back into; it produces
the single result of the lab. `dae lab visualize` prints a `source:` and
`sink:` line so you can see both ends at a glance.

## The four roles

Every module declares exactly one role in its `dae-module.yaml`. The role tells
daedalus how data flows through that module. There are four:

- **emitter** reads your input and fans it out, starting one flight per row. For
  example, reads your target list and yields one flight per star.
- **transform** does ordinary work: reads one input folder, writes one output
  folder, runs once per branch it sits on. For example, fits the transit for one
  target and writes its depth and period.
- **walk-collector** gathers the branches of a *method* back into one result. For
  example, takes the nested-sampling fit and the MCMC fit of the same target and
  reports which model is preferred.
- **flight-collector** gathers the *targets* back into one result. For example,
  waits for every target's fit and writes one population summary across all of
  them.

`fit` and `compare` are not roles; a comparison is the *job* a walk-collector
does, and a fit is the job a transform does.

## Reading `dae lab visualize`

`dae lab visualize` prints a static picture of the recipe. It writes nothing.

The top table lists each module with a role glyph and what it feeds into:

```
legend:  E emitter   T transform   W walk-collector   F flight-collector
source: emit   sink: collect
```

`E`, `T`, `W`, and `F` are the four roles above. `source:` names the emitter and
`sink:` names the final collector.

Below the table is the walk structure:

```
walks
Full:  1-2-[3]
Walks: 1
  walk_1: 1-2-[3]
legend:  {} branch   () walk-collector   [] flight-collector
```

The numbers are the module numbers from the table. The glyphs mark how the walks
join back together:

- `{a,b}` is a branch: the recipe splits into parallel paths here.
- `(n)` is a walk-collector: the branches of a method join here.
- `[n]` is a flight-collector: the per-target flights join here.

**`Full:` is all walks superimposed.** It is the complete branch structure of the
recipe in one line; each `walk_N` below it is one path through that structure. In
a lab that fits each target with two methods and then gathers all targets, you
might see:

```
Full:  1-2-{3,4}-(5)-[6]
Walks: 2
  walk_1: 1-2-3-(5)-[6]
  walk_2: 1-2-4-(5)-[6]
```

The `{3,4}` in `Full:` is the two-method branch; `walk_1` takes module 3 and
`walk_2` takes module 4, and both rejoin at the walk-collector `(5)` and the
flight-collector `[6]`.

## The input file

A fan-out lab reads its targets from a comma-separated file in the lab's
`input/` folder. The `ensemble` example reads `input/targets.csv`, and its
emitter expects two columns:

| Column | Required | Type | Meaning |
| --- | --- | --- | --- |
| `name` | yes | text | The target's identifier, used to label its result. For example `WASP-12 b`. |
| `value` | yes | number | A single numeric quantity per target that the analyze step scores. In `ensemble` it stands in for a per-target measurement (the example uses transit signal-to-noise). |

Further columns (for example `period_days`, `rp_rstar`, `depth_ppm`) are
carried alongside for your own modules to read. The `ensemble` emitter reads
only `name` and `value`, so extra columns do not change its result. One row is
one target, and the emitter starts one flight per row in file order.

The header must be the first line of the file, with no comment line above it.

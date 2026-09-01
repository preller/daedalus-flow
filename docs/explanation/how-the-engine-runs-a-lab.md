# How the engine runs a lab

The recipe in `lab.yaml` describes what to run. This page explains how the
engine turns it into step instances and decides their order.

[Recipe vs run counts](recipe-vs-run-counts.md) explains how a few modules
expand into many step instances; this page covers the rules the engine follows
once that expansion is known.

## Step instances, not modules

The engine does not run *modules*; it runs **step instances**. A step instance
is one module executed for one slice of the work, identified by the module and
the walk it belongs to. The `ensemble` lab has three modules, but a run over
five targets has more step instances: the emitter once, the analysis once per
target, the collector once. Each instance is a distinct unit the engine
schedules.

Each step instance runs once. The engine deduplicates by input lineage, so two
paths that ask for the same work share one run.

## Readiness: a step runs when all its parents are done

The recipe's `depends` fields define which step instances feed which. The engine
turns that into a single rule:

> A step instance is ready to run when **all** of its parents have completed.

It starts with the instances that have no parents, runs them, and as each one
finishes it checks whether that unblocks anything downstream. No run order is
written anywhere; it falls out of the dependencies, so adding a module in the
middle of a chain renumbers nothing.

```{mermaid}
flowchart LR
    emit[emit] --> a1[analyze: target 1]
    emit --> a2[analyze: target 2]
    emit --> a3[analyze: target 3]
    a1 --> collect[collect]
    a2 --> collect
    a3 --> collect
```

The three `analyze` instances have only `emit` as a parent, so all three become
ready the moment `emit` finishes. If `max_workers` allows it, they run together.

## Collectors are barriers

A collector (a walk-collector or a flight-collector) is the join at the bottom
of a fan. Its rule is the same readiness rule, applied to a whole group: it
waits for **every** instance in its group to complete before it runs. That
makes it a *barrier*. In the diagram above, `collect` cannot start until all
three `analyze` instances are done, because all three are its parents. By the
time a collector runs there is nothing left to wait for.

## Waves

When `max_workers` allows parallelism, ready instances run in waves of
`max_workers`; the engine waits for the wave, then recomputes readiness. Wave
membership is reproducible; a slow instance holds its wave.

## Engines

The built-in **local engine** is an in-process scheduler with one bounded
worker pool; `max_workers` sets how many step instances may run at once. It is
always available and needs no extra installation.

The same recipe also runs on the optional **Prefect engine**, which adds a live
run dashboard. The readiness rules above do not change between engines; only
the machinery that runs the ready instances does. See
[run modules in parallel](../how-to/run-modules-in-parallel.md) for how to
switch.

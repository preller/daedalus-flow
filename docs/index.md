---
sd_hide_title: true
---

# daedalus-flow

`daedalus-flow` runs one analysis over a list of targets, compares more than
one method on each target, and keeps a record of every run. Write each step
once, list the steps in a short recipe, and the engine runs every target under
every method. A typical case is a list of planet candidates, each fitted two
different ways, with one summary at the end.

```{mermaid}
flowchart LR
    list[read the target list]
    subgraph t1["target 1"]
        direction LR
        d1[get the data] --> a1[method A]
        d1 --> b1[method B]
        a1 --> c1([compare])
        b1 --> c1
    end
    subgraph t2["target 2"]
        direction LR
        d2[get the data] --> a2[method A]
        d2 --> b2[method B]
        a2 --> c2([compare])
        b2 --> c2
    end
    list --> d1
    list --> d2
    list --> more[... every other target]
    c1 --> all[[summary over all targets]]
    c2 --> all
    more --> all
```

Each box is one step, a small folder holding one Python script that reads a
folder and writes a folder. The recipe lists the steps once; the engine copies
them for every target and every method, runs them in the right order, and
records what ran where.

Deeper in the docs the same picture has its own words. The
[concepts page](explanation/concepts.md) defines each, and the commands below
do not need them yet:

- the recipe and its steps form a [lab](explanation/concepts.md#the-building-blocks)
- each step is a [module](explanation/concepts.md#the-building-blocks)
- each target gets its own [flight](explanation/concepts.md#the-building-blocks)
- each way through the recipe is a [walk](explanation/concepts.md#the-building-blocks)

Install it, then create the smallest lab and run it:

```bash
pip install daedalus-flow
```

```bash
dae example minimal       # writes ./minimal/ (a tiny one-module lab)
cd minimal && dae lab run # runs it under the built-in engine
dae flow status           # reads the latest run back
```

`minimal` runs on the base install; `dae` with no arguments prints the next
step.

| I want to | Page |
| --- | --- |
| install | [Install](tutorials/install.md) |
| run the first lab | [Your first lab](tutorials/getting-started.md) |
| fan out over many targets | [Fan out over many targets](how-to/fan-out-over-many-targets.md) |
| run modules in parallel | [Run modules in parallel](how-to/run-modules-in-parallel.md) |
| isolate module dependencies | [Isolate module dependencies](how-to/isolate-module-dependencies.md) |
| learn the words | [Concepts](explanation/concepts.md) |
| see why a run has more steps than the recipe | [Recipe counts vs run counts](explanation/recipe-vs-run-counts.md) |
| see how the engine runs a lab | [How the engine runs a lab](explanation/how-the-engine-runs-a-lab.md) |
| look up the CLI | [CLI reference](reference/cli.md) |
| look up `lab.yaml` fields | [The lab.yaml manifest](reference/lab-yaml-reference.md) |
| read the JSON envelope | [The `--json` envelope](reference/json-envelope.md) |
| read the outcome codes | [Outcome codes](reference/outcome-codes.md) |
| cite the project | [Citing daedalus-flow](citing.md) |
| contribute | [Contributing](contributing.md) |

```{toctree}
:hidden:
:caption: Get started
tutorials/index
```

```{toctree}
:hidden:
:caption: How-to guides
how-to/index
```

```{toctree}
:hidden:
:caption: Concepts
explanation/index
```

```{toctree}
:hidden:
:caption: Reference
reference/index
```

```{toctree}
:hidden:
:caption: Project
citing
contributing
```

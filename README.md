# daedalus-flow

**Design, validate, and run labs of modules: reproducible analysis pipelines for
data-intensive science.**

[![status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](CHANGELOG.md)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

`daedalus-flow` runs a `lab.yaml` recipe of Python modules in dependency order
and records provenance for every run. It has two main uses: compare methods on
one dataset, and run one analysis across many targets.

> Status: alpha. The command surface and the on-disk lineage format may still
> change before 1.0.

## Quickstart

```bash
dae example minimal       # writes ./minimal/, a one-module lab
cd minimal && dae lab run # runs it under the built-in engine
dae flow status           # reads the latest run back
```

The run writes a provenance tree under `minimal/dae-outputs/`, one folder per
step; the path is printed as `lineage:` when the run finishes. `minimal` needs
nothing beyond the base install, and `dae` with no arguments prints the next
step.

## Install

```bash
pip install daedalus-flow
```

Requires Python 3.12 or newer. The base install pulls in no scientific stack.
The extras add one dependency each:

| Extra | Adds | For |
| --- | --- | --- |
| `demo` | numpy | the `demo` reference lab |
| `engine` | prefect | the Prefect backend, `engine: prefect` in `lab.yaml` |
| `viz` | grandalf | the graph layouts of `dae lab visualize --style` |

```bash
pip install "daedalus-flow[demo]"
```

## Examples

`dae example` lists the bundled labs, simplest first; `dae example <name>`
writes `./<name>/` and prints the next command to run.

| Example | Teaches |
| --- | --- |
| `minimal` | one module, one step: the smallest lab that runs |
| `ensemble` | one input fanned across many targets |
| `parallel` | branches that run side by side, then a barrier join |
| `isolation-nix` | per-module nix environments, two pinned library versions |
| `complex` | a 30-module lab: nested and sibling collectors, a token-solo join |
| `demo` | the exo-survey reference lab: three targets, two fitting methods (needs the `demo` extra) |

`dae module convert script.py` scaffolds a module from an existing script.

## Documentation

[daedalus-flow.readthedocs.io](https://daedalus-flow.readthedocs.io) holds the
tutorials, how-to guides and reference. The same pages live under
[`docs/`](docs/), and `dae --help` covers the commands.

- [Install](docs/tutorials/install.md) and [getting started](docs/tutorials/getting-started.md)
- [Concepts](docs/explanation/concepts.md): labs, modules, walks, flights and roles
- [`lab.yaml` reference](docs/reference/lab-yaml-reference.md), [CLI](docs/reference/cli.md) and the [`--json` envelope](docs/reference/json-envelope.md)
- [Contributing](.github/CONTRIBUTING.md): setup and the `just gate` check

## How to cite

Cite the software with the entry below, or use the "Cite this repository"
button on GitHub, which reads [`CITATION.cff`](CITATION.cff).

```bibtex
@software{daedalus-flow,
  author  = {Reller, Patricio},
  title   = {daedalus-flow: reproducible labs of modules for
             data-intensive science},
  year    = {2026},
  version = {0.1.0},
  url     = {https://github.com/preller/daedalus-flow}
}
```

## Acknowledgments

`daedalus-flow` was developed by Patricio Reller
([ORCID 0000-0003-3161-9239](https://orcid.org/0000-0003-3161-9239)) at the
Centre for Data Intensive Science and Industry, Department of Physics and
Astronomy, University College London. Bruno Merín and Ingo Waldmann advised on
the scientific direction. The work was co-funded by United Kingdom Research and
Innovation (UKRI) through University College London, and by the European Space
Agency (ESA).

## License

[Apache-2.0](LICENSE). The optional `[viz]` and `[engine]` extras pull in MPL-
and EPL-licensed packages.

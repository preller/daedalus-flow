# Install

## Requirements

Requires Python 3.12 or newer. The base install needs no Nix, Docker or system
libraries.

## Install the package

```bash
pip install daedalus-flow
```

This installs the `dae` command and the core engine. The base install pulls in
no scientific stack.

## Verify it worked

```bash
dae --help
```

The output lists the command groups (`example`, `module`, `lab`, and `flow`).
If `dae` is not found, the install location is not on `PATH`; reopen the
terminal, or check where `pip` placed the script.

## Optional extras

A plain install runs every stdlib-only example. Some bundled examples and the
optional orchestration backend sit behind extras:

| Extra | Adds | For |
| --- | --- | --- |
| `demo` | numpy | the `demo` reference lab |
| `engine` | Prefect | the optional Prefect engine and its run dashboard |
| `viz` | grandalf | the graph styles of `dae lab visualize --style` |

Install an extra with the bracket syntax:

```bash
pip install "daedalus-flow[demo]"     # plain install plus the demo extra
pip install "daedalus-flow[engine]"   # plain install plus the Prefect engine
```

The tutorial uses the `minimal` example, which is stdlib-only, so no extra is
needed to follow it. Next: [your first lab](getting-started.md).

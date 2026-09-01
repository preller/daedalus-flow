"""root, brancher_nested: role-only fixture (transform), never run; see tests/fixtures/README.md."""

import daedalus.flow as dae


@dae.entry
def root(ctx: dae.FlowContext) -> None:
    # Never runs; the tests read only the role in dae-module.yaml.
    _ = ctx

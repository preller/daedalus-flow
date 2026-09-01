"""t2, brancher_mixed: role-only fixture (transform), never run; see tests/fixtures/README.md."""

import daedalus.flow as dae


@dae.entry
def t2(ctx: dae.FlowContext) -> None:
    # Never runs; the tests read only the role in dae-module.yaml.
    _ = ctx

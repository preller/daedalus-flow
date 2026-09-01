"""agg, brancher_mixed: role-only fixture (walk_collector), never run; see tests/fixtures/README.md."""

import daedalus.flow as dae


@dae.entry
def agg(ctx: dae.FlowContext) -> None:
    # Never runs; the tests read only the role in dae-module.yaml.
    _ = ctx

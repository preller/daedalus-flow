"""l, brancher_nested: role-only fixture (transform), never run; see tests/fixtures/README.md."""

import daedalus.flow as dae


@dae.entry
def l(ctx: dae.FlowContext) -> None:  # noqa: E743 (entry name matches module id 'l')
    # Never runs; the tests read only the role in dae-module.yaml.
    _ = ctx

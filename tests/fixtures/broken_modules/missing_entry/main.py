# The entry function lacks the @dae.entry decorator; the name and role are valid.
# `dae module validate` must reject this.
"""missing_entry - a transform whose entry function is not decorated."""

import daedalus.flow as dae


def missing_entry(ctx: dae.FlowContext) -> None:
    # Never runs; validation finds no decorated entry first.
    raise NotImplementedError(f"{ctx.step_id}: unreachable (fails validation first)")

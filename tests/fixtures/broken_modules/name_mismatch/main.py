# The entry function is named not_matching, not the directory id name_mismatch;
# the decorator and role are valid. `dae module validate` must reject this.
"""name_mismatch - a decorated entry whose name does not match the directory."""

import daedalus.flow as dae


@dae.entry
def not_matching(ctx: dae.FlowContext) -> None:
    # Never runs; validation refuses the name mismatch first.
    raise NotImplementedError(f"{ctx.step_id}: unreachable (fails validation first)")

# Fully valid main.py: decorated entry, name matches the directory id, minimal
# pass-through body. The defect lives in dae-module.yaml (role: reducer is not
# in the closed role vocabulary).
"""bad_role - a valid pass-through entry paired with an invalid role."""

import daedalus.flow as dae


@dae.entry
def bad_role(ctx: dae.FlowContext) -> None:
    # Never runs; validation refuses the role in dae-module.yaml first.
    raise NotImplementedError(f"{ctx.step_id}: unreachable (fails validation first)")

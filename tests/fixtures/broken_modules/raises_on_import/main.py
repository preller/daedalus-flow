# The entry is decorated and named after the directory; the module body raises
# at import. `dae module validate` must report missing_entry, not a traceback.
"""raises_on_import - a valid entry under a module body that raises at import."""

import daedalus.flow as dae


@dae.entry
def raises_on_import(ctx: dae.FlowContext) -> None:
    # Never runs; the import below the definition raises first.
    raise NotImplementedError(f"{ctx.step_id}: unreachable (fails at import first)")


raise RuntimeError("raises_on_import: the module body raises at import")

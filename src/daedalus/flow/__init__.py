"""daedalus.flow, the public API for writing daedalus modules.

The entire surface a module author needs is ``import daedalus.flow as dae``.
``@dae.entry`` marks a function as a module's entry point, ``dae.FlowContext``
is the object daedalus passes to it, and ``dae.Role`` is the module-role
vocabulary. Everything else in daedalus is internal and may change.
"""

from daedalus.flow._api import FlowContext, Role, entry

__all__ = ["FlowContext", "Role", "entry"]

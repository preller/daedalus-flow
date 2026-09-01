"""The stderr chrome of dae, its teaching notes and Next hints.

stdout carries the transcript only; stderr carries the teaching chrome and the
Next hint. Both helpers print through the shared ``err`` console, so the chrome
picks up the theme. ``next_line`` takes a fixed command string and frames it
with one ``[muted]`` tag; ``note`` carries dynamic content that may contain
``[``, so it prints with markup parsing off.
"""

from .console import err


def next_line(text: str) -> None:
    """Print the stderr Next hint, e.g. ``Next: dae lab visualize``.

    Each command ends with one of these pointing at the next step. ``text`` is
    a fixed command string, so its one ``[muted]`` markup tag stays parsed.
    """
    err.print(f"[muted]Next:[/muted] {text}")


def note(text: str) -> None:
    """Print one line of teaching chrome to stderr.

    One call is one line. Markup parsing is off, so a literal ``[...]`` in the
    message (a ``[viz]`` hint, a bracket in a path) renders verbatim.
    """
    err.print(text, style="muted", markup=False)

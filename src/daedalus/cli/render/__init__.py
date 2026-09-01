"""The Rich render layer over the exemplar data.

Every function prints to the shared ``out`` console; stderr chrome stays on
``err`` in the command bodies. Three private submodules sit behind this face:
``_base`` (grids, sections, glyphs, banners), ``_workflow`` (the onboarding grid
and the module, example and lab-init prose) and ``_topology`` (the structural
reports and the ``--json`` payload builders). A command prints
``preview_banner`` itself under ``--dry-run``, so every render stays single-mode.
"""

from __future__ import annotations

from daedalus.cli.render._ascii_dag import (
    GraphLayoutUnavailable,
    dag_legend,
    draw_dag,
)
from daedalus.cli.render._base import (
    command_grid,
    kv_grid,
    preview_banner,
    report_header,
    section,
)
from daedalus.cli.render._topology import (
    failure_cause,
    flow_status,
    flow_status_payload,
    lab_run_plan,
    lab_run_result,
    lab_validate,
    lab_visualize,
    lab_visualize_for,
    lab_visualize_graph,
    visualize_payload,
    visualize_payload_for,
)
from daedalus.cli.render._workflow import (
    example_ladder,
    lab_init,
    lab_init_done,
    lab_run_plan_payload,
    module_convert_done,
    module_convert_map,
    module_create,
    module_create_done,
    module_try,
    module_validate,
    onboarding,
)

__all__ = [
    "GraphLayoutUnavailable",
    "command_grid",
    "dag_legend",
    "draw_dag",
    "example_ladder",
    "failure_cause",
    "flow_status",
    "flow_status_payload",
    "kv_grid",
    "lab_init",
    "lab_init_done",
    "lab_run_plan",
    "lab_run_plan_payload",
    "lab_run_result",
    "lab_validate",
    "lab_visualize",
    "lab_visualize_for",
    "lab_visualize_graph",
    "module_convert_done",
    "module_convert_map",
    "module_create",
    "module_create_done",
    "module_try",
    "module_validate",
    "onboarding",
    "preview_banner",
    "report_header",
    "section",
    "visualize_payload",
    "visualize_payload_for",
]

"""Dotted outcome codes, one stable code per command result.

A code reads ``dae.<group>.<command>.<result>``, or ``dae.<root>.<result>`` for
the bare onboarding command. tests/test_outcome_contract.py checks every stem
against the live Typer command tree. Tests assert the code and the exit code,
not the rendered text. Each Outcome carries a :class:`Category`, which maps to
the exit code (0 for ok and warning, 1 for failure, 2 for usage).
"""

from enum import Enum, StrEnum, unique


class Category(Enum):
    """The coarse class of an outcome, carrying just its exit code for now."""

    OK = 0
    WARNING = 0  # succeeded with a caveat (exit 0); no render consumer yet
    FAILURE = 1  # the operation produced a failing result
    USAGE = 2  # bad args or an unknown command

    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code


@unique
class Outcome(StrEnum):
    """A stable, dotted outcome code that also carries its :class:`Category`."""

    _category: Category  # per-instance slot set in __new__; not an enum member

    def __new__(cls, code: str, category: Category) -> "Outcome":
        obj = str.__new__(cls, code)
        obj._value_ = code
        obj._category = category
        return obj

    @property
    def category(self) -> Category:
        return self._category

    @property
    def exit_code(self) -> int:
        return self._category.exit_code

    # bare dae onboarding command
    DAE_ONBOARDING_OK = ("dae.onboarding.ok", Category.OK)
    # example group
    EXAMPLE_LIST_OK = ("dae.example.list.ok", Category.OK)
    EXAMPLE_SCAFFOLD_OK = ("dae.example.scaffold.ok", Category.OK)
    EXAMPLE_SCAFFOLD_NOT_FOUND = ("dae.example.scaffold.not_found", Category.USAGE)
    # lab group
    LAB_INIT_OK = ("dae.lab.init.ok", Category.OK)
    LAB_VALIDATE_OK = ("dae.lab.validate.ok", Category.OK)
    LAB_VISUALIZE_OK = ("dae.lab.visualize.ok", Category.OK)
    LAB_RUN_OK = ("dae.lab.run.ok", Category.OK)
    LAB_RUN_DRY_RUN = ("dae.lab.run.dry_run", Category.OK)
    # module group
    MODULE_CREATE_OK = ("dae.module.create.ok", Category.OK)
    MODULE_TRY_OK = ("dae.module.try.ok", Category.OK)
    MODULE_VALIDATE_OK = ("dae.module.validate.ok", Category.OK)
    MODULE_CONVERT_OK = ("dae.module.convert.ok", Category.OK)
    MODULE_CONVERT_DRY_RUN = ("dae.module.convert.dry_run", Category.OK)
    # flow group
    FLOW_STATUS_OK = ("dae.flow.status.ok", Category.OK)
    FLOW_RESUME_OK = ("dae.flow.resume.ok", Category.OK)
    # resume re-ran a failed flow and it failed again (FAILURE, exit 1); the
    # lineage records it like a fresh run failure.
    DAE_FLOW_RESUME_FAILED = ("dae.flow.resume.failed", Category.FAILURE)

    # Per-step failure codes, all FAILURE. They ride on the step's lineage manifest
    # and on the ``error`` cause of a failed run. ``dae.step`` is the one code with
    # no command tree; tests/test_outcome_contract.py declares it as _STEP_GROUP.

    # load_failed: the module never ran (import error, no @dae.entry, or a
    # native-lib dlopen failure).
    DAE_STEP_LOAD_FAILED = ("dae.step.load_failed", Category.FAILURE)
    # execution_failed: the module loaded, then raised while running.
    DAE_STEP_EXECUTION_FAILED = ("dae.step.execution_failed", Category.FAILURE)
    # worker_failed: the worker process died around the module (signal, a bare
    # BrokenPipe with no module traceback, out of memory); the step did not raise.
    DAE_STEP_WORKER_FAILED = ("dae.step.worker_failed", Category.FAILURE)

    # The granular catalog. Category drives the exit code: validate findings are
    # FAILURE, refuse-to-clobber preconditions USAGE, previews and clean OK. A
    # validate not_found is USAGE like example.scaffold.not_found: a bad path.
    DAE_MODULE_VALIDATE_NOT_FOUND = ("dae.module.validate.not_found", Category.USAGE)
    DAE_LAB_VALIDATE_NOT_FOUND = ("dae.lab.validate.not_found", Category.USAGE)
    # try and convert refuse (USAGE) when the module or script does not exist.
    DAE_MODULE_TRY_NOT_FOUND = ("dae.module.try.not_found", Category.USAGE)
    DAE_MODULE_CONVERT_NOT_FOUND = ("dae.module.convert.not_found", Category.USAGE)
    # module validate findings (FAILURE, exit 1)
    DAE_MODULE_VALIDATE_BAD_ROLE = ("dae.module.validate.bad_role", Category.FAILURE)
    DAE_MODULE_VALIDATE_MISSING_ENTRY = (
        "dae.module.validate.missing_entry",
        Category.FAILURE,
    )
    DAE_MODULE_VALIDATE_NAME_MISMATCH = (
        "dae.module.validate.name_mismatch",
        Category.FAILURE,
    )
    # lab validate findings (FAILURE, exit 1). parse_error covers a YAML syntax
    # error, a non-mapping document, or a non-string or duplicate id: found but
    # broken, unlike the run path's USAGE refusal for the same file.
    DAE_LAB_VALIDATE_PARSE_ERROR = ("dae.lab.validate.parse_error", Category.FAILURE)
    DAE_LAB_VALIDATE_CYCLE = ("dae.lab.validate.cycle", Category.FAILURE)
    DAE_LAB_VALIDATE_DANGLING_DEP = ("dae.lab.validate.dangling_dep", Category.FAILURE)
    DAE_LAB_VALIDATE_TWO_EMITTERS = ("dae.lab.validate.two_emitters", Category.FAILURE)
    # Role and structure findings from the static DAG, checked after the cycle
    # check, first defect only. emitter_not_source: a module with `role: emitter`
    # in lab.yaml declares `depends:`; an emitter is the flow's source.
    DAE_LAB_VALIDATE_EMITTER_NOT_SOURCE = (
        "dae.lab.validate.emitter_not_source",
        Category.FAILURE,
    )
    # walk_collector_solo: the on-disk dae-module.yaml role is walk_collector but
    # the module has fewer than two parents, so it converges nothing.
    DAE_LAB_VALIDATE_WALK_COLLECTOR_SOLO = (
        "dae.lab.validate.walk_collector_solo",
        Category.FAILURE,
    )
    # Walk-model validate findings (FAILURE, exit 1), wired into `dae lab validate`.
    # collector_incomplete_group: the collector's incoming token group is not the
    # full branch set of one brancher (a partial, cross-brancher or cross-level merge).
    DAE_LAB_VALIDATE_COLLECTOR_INCOMPLETE_GROUP = (
        "dae.lab.validate.collector_incomplete_group",
        Category.FAILURE,
    )
    # collector_no_walks: every incoming token is the parent or `ROOT` token, so
    # there is nothing to merge; includes a collector's own fan-out reconverging
    # at a second collector.
    DAE_LAB_VALIDATE_COLLECTOR_NO_WALKS = (
        "dae.lab.validate.collector_no_walks",
        Category.FAILURE,
    )
    # walks_reach_flight_collector: a non-root walk token reaches the
    # flight_collector. In v1 the flight_collector takes only the flight root
    # token; a walk_collector has to converge the walks first.
    DAE_LAB_VALIDATE_WALKS_REACH_FLIGHT_COLLECTOR = (
        "dae.lab.validate.walks_reach_flight_collector",
        Category.FAILURE,
    )
    # emitter_multi_successor: the emitter has two or more successors; the flight
    # template needs a single root walk. Insert a transform after the emitter.
    DAE_LAB_VALIDATE_EMITTER_MULTI_SUCCESSOR = (
        "dae.lab.validate.emitter_multi_successor",
        Category.FAILURE,
    )
    # walk_budget_exceeded: the instance count from the token-set pass exceeds the
    # budget (default 1024 per flight). The message names the count and the
    # budget; nothing is truncated.
    DAE_LAB_VALIDATE_WALK_BUDGET_EXCEEDED = (
        "dae.lab.validate.walk_budget_exceeded",
        Category.FAILURE,
    )
    # config_walk_budget_exceeded: the configuration walk count exceeds its budget
    # (default 256). A configuration walk is one choice per brancher plus one per
    # sibling-collector set; a lab under 1024 instances can still have thousands.
    DAE_LAB_VALIDATE_CONFIG_WALK_BUDGET_EXCEEDED = (
        "dae.lab.validate.config_walk_budget_exceeded",
        Category.FAILURE,
    )
    # reserved_separator_in_id: a module id contains `@`. Instance ids read
    # `<module>@w<id>`, so a `@` in a module id makes the instance id ambiguous.
    DAE_LAB_VALIDATE_RESERVED_SEPARATOR_IN_ID = (
        "dae.lab.validate.reserved_separator_in_id",
        Category.FAILURE,
    )
    # isolation_unbacked: the declared isolation has no working closure. Statically,
    # the preference ships no files to build from (for a ladder, no entry). Under
    # `validate --deep`, the closure fails to build or import; the cause rides `error`.
    DAE_LAB_VALIDATE_ISOLATION_UNBACKED = (
        "dae.lab.validate.isolation_unbacked",
        Category.FAILURE,
    )
    # nothing_to_nixify: under `isolation: nix` a module has none of flake.nix,
    # uv.lock or a non-empty requirements.txt, so uv2nix has nothing to build.
    # Buildability is not checked; a flake without a toolchain fails at provisioning.
    DAE_LAB_VALIDATE_NOTHING_TO_NIXIFY = (
        "dae.lab.validate.nothing_to_nixify",
        Category.FAILURE,
    )
    # lab run family. The run path refuses as USAGE (exit 2) when there is no lab,
    # the lab is defective, or the serial engine cannot run it. A module raising
    # mid-run is FAILURE (exit 1) and the lineage records it.
    DAE_LAB_RUN_NOT_FOUND = ("dae.lab.run.not_found", Category.USAGE)
    DAE_LAB_RUN_INVALID = ("dae.lab.run.invalid", Category.USAGE)
    DAE_LAB_RUN_UNSUPPORTED = ("dae.lab.run.unsupported", Category.USAGE)
    DAE_LAB_RUN_FAILED = ("dae.lab.run.failed", Category.FAILURE)
    # missing_deps: a started run hit a module whose top-level third-party import
    # is absent from the environment; the message points at the module's
    # requirements.txt. Gated on find_spec, so a broken install stays run.failed.
    DAE_LAB_RUN_MISSING_DEPS = ("dae.lab.run.missing_deps", Category.FAILURE)
    # engine_unavailable: the lab selected `engine: prefect` but the PrefectEngine
    # extra is not installed. The engine selector (cli/commands/lab/) refuses
    # before any write, naming `pip install daedalus-flow[engine]`.
    DAE_LAB_RUN_ENGINE_UNAVAILABLE = (
        "dae.lab.run.engine_unavailable",
        Category.FAILURE,
    )
    # isolation_unavailable: the lab set `isolation: nix` but nix cannot run on
    # this host (nix is a host prerequisite, not a pip dep). The precondition
    # check (cli/commands/lab/) refuses before any write rather than fall back to uv.
    DAE_LAB_RUN_ISOLATION_UNAVAILABLE = (
        "dae.lab.run.isolation_unavailable",
        Category.FAILURE,
    )
    # ok_empty: the emitter yielded an empty partition (M=0); the run completed
    # with zero flights and no flights/ dir. Distinct from lab.run.ok so a caller
    # can tell a real fan-out from a no-op.
    DAE_LAB_RUN_OK_EMPTY = ("dae.lab.run.ok_empty", Category.OK)
    # flow status empty query (OK, exit 0): no dae-outputs/flows/ here; reuses the
    # ``nothing`` leaf (lab.clean.nothing).
    DAE_FLOW_STATUS_NOTHING = ("dae.flow.status.nothing", Category.OK)
    # resume found nothing to resume (OK, exit 0): no flow here, or the latest flow
    # already completed. Reuses the ``nothing`` leaf like flow.status.nothing.
    DAE_FLOW_RESUME_NOTHING = ("dae.flow.resume.nothing", Category.OK)
    # refuse-to-clobber preconditions (USAGE, exit 2)
    DAE_LAB_INIT_EXISTS = ("dae.lab.init.exists", Category.USAGE)
    DAE_MODULE_CREATE_EXISTS = ("dae.module.create.exists", Category.USAGE)
    DAE_MODULE_CONVERT_EXISTS = ("dae.module.convert.exists", Category.USAGE)
    DAE_EXAMPLE_SCAFFOLD_EXISTS = ("dae.example.scaffold.exists", Category.USAGE)
    # scaffold dry-run previews (OK, exit 0)
    DAE_LAB_INIT_DRY_RUN = ("dae.lab.init.dry_run", Category.OK)
    DAE_MODULE_CREATE_DRY_RUN = ("dae.module.create.dry_run", Category.OK)
    # lab clean family (OK, exit 0)
    DAE_LAB_CLEAN_OK = ("dae.lab.clean.ok", Category.OK)
    DAE_LAB_CLEAN_DRY_RUN = ("dae.lab.clean.dry_run", Category.OK)
    DAE_LAB_CLEAN_NOTHING = ("dae.lab.clean.nothing", Category.OK)

# Outcome codes

Generated from `daedalus.core.outcomes` by
`scripts/gen_outcome_catalog.py`. Do not edit by hand: change the codes and
regenerate. Each code is the stable `--json` `code` value; `exit` is the
process exit status the category carries.

| code | category | exit |
| --- | --- | --- |
| `dae.example.list.ok` | OK | 0 |
| `dae.example.scaffold.exists` | USAGE | 2 |
| `dae.example.scaffold.not_found` | USAGE | 2 |
| `dae.example.scaffold.ok` | OK | 0 |
| `dae.flow.resume.failed` | FAILURE | 1 |
| `dae.flow.resume.nothing` | OK | 0 |
| `dae.flow.resume.ok` | OK | 0 |
| `dae.flow.status.nothing` | OK | 0 |
| `dae.flow.status.ok` | OK | 0 |
| `dae.lab.clean.dry_run` | OK | 0 |
| `dae.lab.clean.nothing` | OK | 0 |
| `dae.lab.clean.ok` | OK | 0 |
| `dae.lab.init.dry_run` | OK | 0 |
| `dae.lab.init.exists` | USAGE | 2 |
| `dae.lab.init.ok` | OK | 0 |
| `dae.lab.run.dry_run` | OK | 0 |
| `dae.lab.run.engine_unavailable` | FAILURE | 1 |
| `dae.lab.run.failed` | FAILURE | 1 |
| `dae.lab.run.invalid` | USAGE | 2 |
| `dae.lab.run.isolation_unavailable` | FAILURE | 1 |
| `dae.lab.run.missing_deps` | FAILURE | 1 |
| `dae.lab.run.not_found` | USAGE | 2 |
| `dae.lab.run.ok` | OK | 0 |
| `dae.lab.run.ok_empty` | OK | 0 |
| `dae.lab.run.unsupported` | USAGE | 2 |
| `dae.lab.validate.collector_incomplete_group` | FAILURE | 1 |
| `dae.lab.validate.collector_no_walks` | FAILURE | 1 |
| `dae.lab.validate.config_walk_budget_exceeded` | FAILURE | 1 |
| `dae.lab.validate.cycle` | FAILURE | 1 |
| `dae.lab.validate.dangling_dep` | FAILURE | 1 |
| `dae.lab.validate.emitter_multi_successor` | FAILURE | 1 |
| `dae.lab.validate.emitter_not_source` | FAILURE | 1 |
| `dae.lab.validate.isolation_unbacked` | FAILURE | 1 |
| `dae.lab.validate.not_found` | USAGE | 2 |
| `dae.lab.validate.nothing_to_nixify` | FAILURE | 1 |
| `dae.lab.validate.ok` | OK | 0 |
| `dae.lab.validate.parse_error` | FAILURE | 1 |
| `dae.lab.validate.reserved_separator_in_id` | FAILURE | 1 |
| `dae.lab.validate.two_emitters` | FAILURE | 1 |
| `dae.lab.validate.walk_budget_exceeded` | FAILURE | 1 |
| `dae.lab.validate.walk_collector_solo` | FAILURE | 1 |
| `dae.lab.validate.walks_reach_flight_collector` | FAILURE | 1 |
| `dae.lab.visualize.ok` | OK | 0 |
| `dae.module.convert.dry_run` | OK | 0 |
| `dae.module.convert.exists` | USAGE | 2 |
| `dae.module.convert.not_found` | USAGE | 2 |
| `dae.module.convert.ok` | OK | 0 |
| `dae.module.create.dry_run` | OK | 0 |
| `dae.module.create.exists` | USAGE | 2 |
| `dae.module.create.ok` | OK | 0 |
| `dae.module.try.not_found` | USAGE | 2 |
| `dae.module.try.ok` | OK | 0 |
| `dae.module.validate.bad_role` | FAILURE | 1 |
| `dae.module.validate.missing_entry` | FAILURE | 1 |
| `dae.module.validate.name_mismatch` | FAILURE | 1 |
| `dae.module.validate.not_found` | USAGE | 2 |
| `dae.module.validate.ok` | OK | 0 |
| `dae.onboarding.ok` | OK | 0 |
| `dae.step.execution_failed` | FAILURE | 1 |
| `dae.step.load_failed` | FAILURE | 1 |
| `dae.step.worker_failed` | FAILURE | 1 |

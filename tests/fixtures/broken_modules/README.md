# Broken Modules

Invalid module fixtures for validator-failure tests. Each directory is one
module that is valid and minimal except for a single defect, so a test can pin
the validator to one error at a time. `broken_labs/` holds the invalid
`lab.yaml` specs; here the unit under test is the per-module surface,
`main.py` plus `dae-module.yaml`, not a whole lab.

| directory | intended defect | expected validator error |
| --- | --- | --- |
| `missing_entry/` | the entry function has no `@dae.entry` decorator | no `@dae.entry` entry point found in the module |
| `bad_role/` | `dae-module.yaml` declares `role: reducer` | role `reducer` is not in the closed role vocabulary (emitter, transform, walk_collector, flight_collector) |
| `name_mismatch/` | the entry function is named `not_matching`, not `name_mismatch` | entry function name must equal the module directory id `name_mismatch` |
| `no_main/` | no `main.py` at all, only the manifest | `dae.module.validate.missing_entry`, not a crash on the absent file |
| `raises_on_import/` | the module body raises at import time | `dae.module.validate.missing_entry`, not a traceback |

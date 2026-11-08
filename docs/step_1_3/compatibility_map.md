# T13-01: actual interface audit

Base: b510177725075ce549ef5d5fca8bcf050ab8ed03. The generated synthetic
bundle shape in synthetic_manifest_shape.json was captured by executing the
existing setup/build_plan/materialize/verify_bundle path, not copied from DD.
No private HPC bundle was accessed. The operator's actual f/d mode is preserve_source.

| DD role | Actual Step 1-2 contract | Step 1-3 adapter |
|---|---|---|
| INPUT_READY | preparations.state; result.result | Existing tables/rows unchanged |
| Verify | ai_chem_input.prepare.verify_bundle(Path, deadline=None) -> dict | preflight.verify_prepared_bundle calls it directly |
| Manifest | provenance/manifest.json; schema_version/hash_schema_version=1 | Exact expected hash; no rewriting |
| READY | schema_version, calculation_id, stage_id, request_digest, manifest_sha256 | Existing verifier, additional request-stage check |
| Science | science_identity.method_hash/configuration_hash/stage_input_hash | Scientific identity + pinned refs + generator/VASP version |
| Resources | resource_request.queue/pe/slots/quota_static/live_checked | all.q/mpi_32/32/320 are declared, not actual SGE precedence evidence |
| Script | run_script.mode, byte_identical, resource_validation | preserve_source is opaque; no -V/node equivalence inferred |
| Used config | provenance/resolved_config.json | Read-only exact profile/material/template snapshot |
| Roots | profile.roots.source/protected/output/registry/state/lock | Same guards; submission state/lock/output must match pinned profile |
| State | state/preparations.sqlite3; schema_meta=1 | Add submission_* tables; retain preparation schema/version/rows |
| Lock | lock/controller.lock, global_lock(root) | Shared single writer; no second independent controller |
| Errors | InputError(code,field,exit_code) | Sanitized submission results/exit mapping |
| CLI/worker | ai_chem_input CLI; preparation worker has no scheduler path | Add python -m ai_chem_input.submission; old source/CLI untouched |

The subpackage CLI is an additive namespace, not an independent state/lock
controller. pyproject package data is extended only for the new schemas. Old
source, scientific schema, preparation workers and Input payloads are not edited.
The old Step 1-2 "no runtime subprocess imports" test scans its original top-level
modules; scheduler subprocesses are confined to the new submission subpackage.

S13-15 is not established by static script parsing: -clear and -q all.q can alter
source -V and all.q@node127 behavior. Script/command/client-env-bound local evidence,
explicit changed-environment approval and an authorized benign local pilot are
required before dispatch. Missing evidence blocks before any dispatch fence.

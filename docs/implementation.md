# Implementation and evidence

T01–T11 implementation paths and synthetic validation are present. T12 provides
regression/evidence tooling and local handoff; its **AC12 exact-platform and AC13
actual-template gates remain NOT RUN**, so full HPC acceptance is not claimed.

| Task | Implementation | Synthetic evidence |
|---|---|---|
| T01 | config/errors/paths, package metadata, private artifact policy | test_t01: JSON/schema, overlap/prefix, symlink, FIFO, hardlink/traversal |
| T02 | discovery/registry, exact refs and exclusive revisions | test_t02: immutable registration, limits/ambiguity, missing source |
| T03 | INCAR span lexer/parser/typed patch | test_t03: duplicates, comments/quotes/CRLF/continuation/repetition, REMOVE/idempotence |
| T04 | POSCAR/POTCAR/KPOINTS parsers | test_t04: ordered blocks, scale/selective/unsupported/truncation |
| T05 | protocols/material validators | test_t05_t07, test_validation_matrix: f/d, U/block/potential/moment/spin/static checks |
| T06 | fail-closed restart provider and pinned local store consumer | test_t06: valid synthetic A→B/B→C, incompatibility/revocation/header/hash |
| T07 | fixed typed run.sh renderer | profile/injection tests, independent literal golden |
| T08 | raw/canonical hashes, snapshots, semantic/text diff, manifest/READY | bundle verification/tampering and raw-hash tests |
| T09 | immutable pure plan, revalidation, private atomic materializer | CLI tree snapshot, write/rename/partial-copy/corruption/deadline faults |
| T10 | SQLite schema/intents/events/attempts, lock, per-identity reconciliation | crash points, FK, idempotency/conflict, two-process writers, missing final |
| T11 | strict CLI exit contract and one-shot worker | CLI/worker: malformed/symlink/re-delivery/minimal environment/busy |
| T12 | goldens, actual-outcome acceptance runner, target smoke and local golden tool | test_t12; AC12/AC13 are separate unrun gates |

`docs/evidence/acceptance-matrix.json` records selected **executed** tests and
actual outcomes by acceptance ID, plus unrun local gates. It is traceability,
not an exhaustive proof that every possible hostile filesystem/DB failure was
simulated. Test fixtures never encode actual Eu2BaCuO5/CaCu(SeO3)2 cells or approved
scientific values. Independent golden files were written as literal expected
text; the renderer does not generate expected test results.

Source preservation tests compare bytes/mode/mtime before and after both successful
and faulted preparation, and verify different output inodes. Dry-run tests compare
the full temporary source/config/output/state/lock/inbox tree without creating
SQLite or lock artifacts. Faults retain source and incomplete private staging.
The crash matrix covers intent, copy, manifest/READY, pre-rename, post-rename and
post-DB success; recovery validates hashes before marking INPUT_READY.

Runtime operation spies prohibit subprocess and socket creation during synthetic
planning/materialization. No production module imports network/subprocess clients.
These checks distinguish rendered launcher strings from actual invocation.

Hash domains are versioned and separate: raw exact bytes; resolved request intent
excluding transport request_id; method; atom/configuration; scientific stage;
and payload inventory. Output path/time are outside the scientific stage hash.
Transport redelivery does not rewrite the existing bundle. Same identity with a
changed material/template/profile/protocol revision or intent is a conflict.

Changed file groups are `src/ai_chem_input/*.py`, runtime/catalog schemas and draft
examples, synthetic fixture/unit/integration tests, `tools/`, package/dev metadata,
README and operator/evidence docs. No pre-existing application code or research
file was modified. The initial checkout had no commits/files; no commit, push or
remote repository update is performed by this task.

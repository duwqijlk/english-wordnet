# Daily learning-gloss maintenance

## Two branches, one source version

- `main` is upstream-only reference history. Fetching upstream does not change our dictionary automatically.
- `learning-glosses/base-2025` is our accumulating maintenance branch, not the untouched source baseline.
- `2025-edition` and `LEARNING_SOURCE.json` identify the original source commit. The config is recorded once for the whole repository; never move the tag to make checks pass.

Each task starts a temporary branch at the current maintenance tip, receives a reviewed PR, merges back and deletes the temporary branch. Part completion tags are immutable checkpoints. Do not add a third permanent branch or rewrite old history for tidiness.

## One sense, one editable YAML

The current schema is `oewn-learning-gloss-v2`:

```yaml
schema: oewn-learning-gloss-v2
senseId: existing OEWN sense ID
synsetId: existing OEWN synset ID
simpleMeaning: A clear, accurate learner definition.
scope: Source-supported sense boundaries or other names.
examples:
  - A natural example of this sense.
  - Another natural example of this sense.
editorialStatus: reviewed-model-not-student-validated
sourceBatch: 123
reviewVerdict: second-pass
```

No per-record archive, definition, row or batch hashes are required. `sourceBatch` records origin, not a record-set seal. Editing one gloss does not require modifying sibling records, updating a hash inventory or rebuilding SQLite.

Git commits identify exact content; PRs record reasons and review; tags identify releases. Hash-bearing records and review files in old commits or immutable pilot `manifest.json` / `lineage/` remain historical evidence, not an active update index. Do not delete old evidence or pretend a model review means teacher/student validation.

## Editing and incoming packs

1. Identify the exact existing sense and inspect its source definition, synset binding and related senses.
2. Edit only its learning YAML; never change `src/yaml/` original definitions, create a sense ID or hand-edit deployed databases/JSON.
3. Preserve accuracy, restrictions, natural examples and useful scope. Do not invent exclusions or distort facts merely to avoid a headword component.
4. Freeze the change in a commit. An independent reviewer must review that actual commit, not an unspecified earlier draft. If the text changes, obtain confirmation of the new revision.
5. Run source/format checks and compare the exact sense-ID sets. Check the PR diff contains only intended learning changes.
6. Merge, retain the PR/commit and clean up the temporary branch.

External parts 9, 13, 14 and 15 already in progress may retain their old draft/review/hash delivery format. Do not send them back merely for this schema migration. The receiving adapter checks the old inputs, records their untouched evidence, and emits v2. New repair handoffs identify the baseline maintenance commit and expected previous field values rather than creating fresh row hashes. If either differs, stop and reconcile; no blind overwrite. Already-issued legacy row-hash patches can be compared against the recorded pre-migration Git commit and current text without adding hashes back to active records.

## Validation and optional builds

`LEARNING_SOURCE.json` centrally pins the source commit. Validation compares source YAML and license notices with that Git snapshot and checks actual sense IDs, filenames, synset bindings, schema and content. This replaces per-gloss source hashes, not source verification. Source file edits must fail validation even when an existing sense still exists.

Run the trusted script with isolated Python from outside the downloaded checkout:

```bash
python -I -X utf8 local-resources/oewn-2025-upstream-clone/scripts/check_learning_glosses.py --repo local-resources/oewn-2025-upstream-clone
```

The checker validates structure and source identity, not meaning or reviewer identity. Editorial review is separate. Compare catalog, emitted YAML and Git-tree sense-ID/path sets before publishing: ignore patterns can hide a file.

SQLite is an optional derived query/offline artifact, not the editing source and not required for each batch. Each build records both the upstream `sourceCommit` and our `learningCommit` centrally in database metadata and its report. Builds require committed, clean source/gloss/config/tool paths and recheck that state before publishing the output; commit changes first rather than labeling dirty content with an unrelated commit. The builder discovers current YAML; it does not need updated pilot-manifest hashes. Build only when a deliverable is needed. Old readers may retain a deprecated empty hash-named compatibility column; it is not an active verification mechanism.

## A later source release

Create a separate version directory and a new version integration branch for a verified source release. Preserve the 2025 branch and original tag. Compare sense existence, sense-to-synset mappings, definitions, POS/forms, relevant relations/context and license changes; an unchanged ID alone does not prove compatibility. Re-review affected glosses and quarantine removed/split/ambiguous mappings. Existing books retain their release pin until explicitly migrated.

## Rollback

Use Git/PR history to revert an intended change. Disjoint additions usually revert independently; later edits to the same file can conflict. Reconcile the local maintenance catalog as well. Deleting a branch is not rollback, and a clean revert is not proof of semantic correctness.

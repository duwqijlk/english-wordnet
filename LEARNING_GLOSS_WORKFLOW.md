# Daily learning-gloss maintenance in this fork

**One Git repository, one editable record per OEWN sense.** To simplify a particular sense, change only its file under `src/learning-glosses/<URL-quoted senseId>.yaml`. Do not edit the official `src/yaml/` synset definition, the release JSON ZIP, a SQLite database, or the migration manifest for an ordinary wording edit. The `manifest.json` and `lineage/` directory are the immutable 2025 pilot import ledger, not a second daily-maintained index.

Each gloss record retains its existing `senseId`, `synsetId`, original archive/definition hashes, separate learning `simpleMeaning`, editorial `scope`, and examples. Editing the gloss never changes the original sense→synset relation. A pull request should show the single file's diff, explain why the original was difficult and how the new wording preserves meaning, and include actual editorial review. The current `reviewed-model-not-student-validated` label is historical, not a human authorization or student acceptance signal. GitHub PR approvals, branch protection and CI rules still need configuring on the fork; they are not supplied by a label in YAML.

Build process: validate upstream YAML sense identity and all learning-gloss original-definition hashes; enumerate `*.yaml` directly; produce an immutable read-only SQLite with original and reviewed meaning keyed by sense ID. The SQL is a query artifact, not an editing surface. The build discovers new gloss files automatically and hashes the current content into metadata, so **changing one gloss does not require changing 3,412 manifest hashes**. A missing old imported file is rejected to avoid silent disappearance; intentional withdrawal needs an explicit reviewed migration process. The pure source check is `scripts/check_learning_glosses.py --repo PATH` (YAML/original ID/formal structure; not meaning approval). The reviewed SQL builder is included at `scripts/build_learning_sql.py`. Run it with Python -I from outside the downloaded checkout; current CI integration and branch protections have not been configured. Every build recomputes the source-file inventory rather than requiring manifest edits for one gloss.

Upgrading OEWN upstream is a separate migration: compare original sense IDs, synset links, definitions, forms and license notice changes. If an original definition changes, re-review dependent glosses instead of silently carrying forward. Existing books pin a dictionary release; a newly built SQL does not rewrite their meanings by itself.

Local command (run Python -I from the englishbook project root, not inside this downloaded checkout):

```bash
python -I -X utf8 local-resources/oewn-2025-upstream-clone/scripts/build_learning_sql.py --repo local-resources/oewn-2025-upstream-clone --out local-exports/NEW-release.sqlite --report local-exports/NEW-release-report.json
```

The exact 2025 YAML tag matches the initially downloaded JSON on synset IDs, definitions, lexical sense mappings and declared forms. That comparison does not establish learner correctness. Reviewed batches are published by internal PRs in `duwqijlk/english-wordnet`; this is not an upstream submission or a production API deployment.

## Branches and checkpoints

Keep two long-lived branches:

- `main`: upstream-only tracking branch. Never merge learning-gloss work into it.
- `learning-glosses/base-2025`: the accumulating 2025 learning-gloss integration branch, not an untouched source baseline.

The immutable source baseline is tag `2025-edition` (`dc343f2683279ecbb13fab4e2fd778d7b162d287`). Do not move this tag or merge a later OEWN release into `base-2025`.

Start each temporary work branch at the current integration tip. After review, validation and PR merge, remove the work branch locally and on the fork, but only after checking that its exact tip is an ancestor of the integration branch and it has no independent work. Ancestry through earlier merged batches is normal; do not rewrite history merely to make batches appear independent. Keep `part-N` completion tags at the corresponding merge commits, and give later polish work its own checkpoint rather than moving an existing tag. An outstanding external pack is data, not a branch: parts 9, 13, 14 and 15 keep their assigned rows and numbers through repository cleanup.

A revert is an inverse change, not a branch deletion. Disjoint added sense files can usually be reverted independently; later edits to the same files may require resolution. Rollback must also reconcile the local maintenance catalog and audit records. Neither a tag nor a clean Git revert proves that the resulting dictionary is semantically correct.

Before publishing a batch, compare the exact sense-ID/filename sets in the catalog, emitted YAML and Git tree, not only their counts. Ignore rules can hide an otherwise valid file. Run the source checker, and keep the result separate from the content-review evidence. Do not rebuild SQLite for routine batches unless a deliverable is needed.

## A later OEWN release

Create a separate version directory and a new integration branch such as `learning-glosses/base-2026`, based on the verified new source release. Preserve the 2025 branch, source tag and release pins. Migration must compare sense existence, sense-to-synset links, lemma/POS/forms, original definitions, relevant relations/usage context and license notices. A sense ID or an unchanged definition hash alone is not sufficient proof of compatibility. Re-review affected glosses; quarantine removed, split or ambiguous mappings rather than inventing identifiers. Rebind archive/definition hashes only after checking against the new source, never simply to make validation pass.

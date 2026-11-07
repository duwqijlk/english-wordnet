# Daily learning-gloss maintenance in this fork

**One Git repository, one editable record per OEWN sense.** To simplify a particular sense, change only its file under `src/learning-glosses/<URL-quoted senseId>.yaml`. Do not edit the official `src/yaml/` synset definition, the release JSON ZIP, a SQLite database, or the migration manifest for an ordinary wording edit. The `manifest.json` and `lineage/` directory are the immutable 2025 pilot import ledger, not a second daily-maintained index.

Each gloss record retains its existing `senseId`, `synsetId`, original archive/definition hashes, separate learning `simpleMeaning`, editorial `scope`, and examples. Editing the gloss never changes the original sense→synset relation. A pull request should show the single file's diff, explain why the original was difficult and how the new wording preserves meaning, and include actual editorial review. The current `reviewed-model-not-student-validated` label is historical, not a human authorization or student acceptance signal. GitHub PR approvals, branch protection and CI rules still need configuring on the fork; they are not supplied by a label in YAML.

Build process: validate upstream YAML sense identity and all learning-gloss original-definition hashes; enumerate `*.yaml` directly; produce an immutable read-only SQLite with original and reviewed meaning keyed by sense ID. The SQL is a query artifact, not an editing surface. The build discovers new gloss files automatically and hashes the current content into metadata, so **changing one gloss does not require changing 3,412 manifest hashes**. A missing old imported file is rejected to avoid silent disappearance; intentional withdrawal needs an explicit reviewed migration process. The pure source check is `scripts/check_learning_glosses.py --repo PATH` (YAML/original ID/formal structure; not meaning approval). The reviewed SQL builder is included at `scripts/build_learning_sql.py`. Run it with Python -I from outside the downloaded checkout; current CI integration and branch protections have not been configured. Every build recomputes the source-file inventory rather than requiring manifest edits for one gloss.

Upgrading OEWN upstream is a separate migration: compare original sense IDs, synset links, definitions, forms and license notice changes. If an original definition changes, re-review dependent glosses instead of silently carrying forward. Existing books pin a dictionary release; a newly built SQL does not rewrite their meanings by itself.

Local command (run Python -I from the englishbook project root, not inside this downloaded checkout):

```bash
python -I -X utf8 local-resources/oewn-2025-upstream-clone/scripts/build_learning_sql.py --repo local-resources/oewn-2025-upstream-clone --out local-exports/NEW-release.sqlite --report local-exports/NEW-release-report.json
```

The exact 2025 YAML tag matches the initially downloaded JSON on synset IDs, definitions, lexical sense mappings and declared forms. That comparison does not establish learner correctness. No production API, remote deploy, public fork branch or PR has been published from this checkout yet.

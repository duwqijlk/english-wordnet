# Learning glosses: additive OEWN layer

This fork keeps the complete OEWN source in `src/yaml/` and a separate learner-facing layer in `src/learning-glosses/`. One existing sense has one YAML file. Original definitions and sense identifiers are not overwritten.

## Source and record format

`LEARNING_SOURCE.json` pins OEWN 2025 once at upstream commit `dc343f2683279ecbb13fab4e2fd778d7b162d287` (`2025-edition`). Validation compares the source tree to that exact Git snapshot. The current per-sense format is `oewn-learning-gloss-v2`, without repeated archive/definition/batch hashes. Each record retains its sense/synset identity, learning meaning, scope, examples, model-review status, source batch and review verdict.

Version and review provenance belong in Git commits, PRs and release tags. A one-sense edit must not cascade into updates of every sibling in its old batch. Older commits retain the v1 fields; no history is rewritten.

The initial pilot's `manifest.json` and `lineage/` preserve its 3,412-record migration snapshot. They are historical evidence, not current coverage or a daily edit checklist. Enumerate current YAML and run the checker for live coverage. Model-reviewed does not mean human/student validated.

## Maintenance and publication

The long-lived branches are `main` (upstream-only reference) and `learning-glosses/base-2025` (our maintenance line). Temporary work branches merge by PR and are deleted after verification. See [LEARNING_GLOSS_WORKFLOW.md](LEARNING_GLOSS_WORKFLOW.md) for edits, old external-pack compatibility, validation and future migration.

Git YAML remains the maintenance source. SQLite and any future R2 JSON release are derived artifacts, not editing surfaces. A complete published dictionary retains all source senses: a learning gloss overrides the displayed definition when present; otherwise the original definition remains available. No R2 publication or production deployment is implied by a Git merge.

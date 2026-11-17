# Changelog

All notable changes to this project should be recorded here. The project has not yet published a semantic version.

## [Unreleased]

### Added

- Production-readiness evidence and explicit M9 no-go recommendation with unresolved gates.
- README architecture diagrams and principle/control mappings.
- Technical-debt register, contributor guidance and release notes file.

### Changed

- README links now include the security, operations and readiness documents.

### Verification notes

- M9 local suite: 115 passed; branch-aware coverage 83%.
- `alembic check` on a fresh disposable PostgreSQL schema reports an index/metadata mismatch; see [TD-001](docs/TECH_DEBT.md#technical-debt-and-release-gates).
- No staging deployment, load/soak, restore, alert, browser accessibility or production release was verified.

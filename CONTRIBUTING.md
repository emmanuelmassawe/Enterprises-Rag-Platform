# Contributing

## Before changing the project

Read [AGENTS.md](AGENTS.md), the relevant sections of [the brief](docs/BRIEF.md), [requirements](docs/REQUIREMENTS.md), [API design](docs/API_DESIGN.md), [architecture](docs/ARCHITECTURE.md), and the applicable ADRs. Requirements, API contracts and approved architecture decisions change only through an owner-approved ADR and synchronized docs.

## Local workflow

1. Install Python 3.12, `uv`, Node.js for `web/`, and Docker Compose if running integration services.
2. Run `uv sync --all-groups` and copy `.env.example` to an ignored `.env`; never put credentials in Git.
3. Use the documented `make setup`, `make dev`, `make test`, `make lint`, `make typecheck`, `make redteam` and `make eval` workflows. Evaluation/load commands need explicit synthetic or non-production inputs.
4. For web changes, use the lockfile (`npm ci`) and run the web lint, typecheck, tests and production build scripts.
5. Before commit, run the relevant static checks, tests and `git diff --check`. Keep docs, diagrams, traceability and ADRs synchronized with code.

## Engineering expectations

- Keep domain code independent from adapters and HTTP; services depend on ports.
- Validate boundaries, keep resource bounds and timeouts explicit, use stable problem-details errors, and test failure behavior.
- Use synthetic or licensed fixtures only. Never add customer data, secrets, production identifiers, or provider output containing sensitive data.
- Do not use production credentials or run `terraform apply`; deployment applies happen through protected CI with owner approval.
- Do not weaken or rename tests to make a change pass. Explain any skipped verification in the PR.
- Use Conventional Commits. Include behavior, verification evidence, risks, and linked requirement/ADR IDs in pull requests.

## Security reports

Do not file secrets or sensitive exploit details in public repository issues. Contact the repository owner through the organization's approved private security reporting channel. Do not use this repository to store credentials or state files.

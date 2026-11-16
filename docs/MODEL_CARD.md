# Model Card

## Current intended use

The service answers user questions from tenant-authorized, indexed PDF source material through a fixed retrieval-and-generation pipeline. It is a decision-support and information-retrieval aid. Users must check the cited source before acting on an answer.

## Models

| Role | Config | Current proposed value | Status |
|---|---|---|---|
| Text embedding | `EMBEDDING_MODEL` | `gemini-embedding-2` | Proposed; owner must confirm exact model, dimensions, region and data terms. |
| Answer generation | `GENERATION_MODEL` | `gemini-3.8-flash` | Proposed; owner must confirm exact supported model/version and data terms. |

No weights are hosted in this repository. Provider responses use configured timeouts, strict structured output and bounded token limits. The model receives no tools or actions.

## Known limitations

- Retrieval can omit relevant documents or return misleading but similar passages.
- Citation membership proves that an ID was retrieved, not that every natural-language claim is entailed by that text.
- The injection detector is heuristic. Adversarial paraphrase and visual PDF instructions can evade it.
- English PostgreSQL full-text search and text-based PDF extraction limit language and document coverage.
- No independent groundedness evaluator is enabled until the M6 evaluation harness.
- Current proposed provider model IDs and dimensions have not been validated against the owner's production account.

## Privacy and monitoring

Provider region, retention/training terms and compliance/DPA are owner approval gates. LangSmith is disabled by default and, when enabled, receives allowlisted metadata only. See [AI security](AI_SECURITY.md) and [ADR-015](ADR/ADR-015-milestone-5-observability-security.md).

## Change management

Pin model identifiers and review an upgrade with the synthetic red-team suite and M6 evaluation set before deployment. A model, prompt or retrieval change that affects the approved contract requires an ADR and owner approval.

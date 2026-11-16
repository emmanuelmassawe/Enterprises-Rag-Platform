# AI Security

Status: M5 controls are implemented in the request path as defense in depth. This heuristic suite is not proof that prompt injection is solved. Production ingestion remains blocked on owner decisions and the open controls listed below.

## Threat model

The model receives a user question and retrieved, untrusted source text. It has no tools, filesystem, network access or write actions. Assume the model may follow malicious instructions from either input. The security boundary is application authorization, PostgreSQL RLS, strict output validation, citation membership and output handling. Prompt text is not an authorization boundary.

Threats include direct and indirect prompt injection, jailbreaks, poisoned or manipulated source text, cross-tenant retrieval, PII and credential disclosure, system-prompt disclosure, unsafe rendering, ungrounded answers, provider/package compromise, and unbounded cost or queue work.

## Control inventory

| Control | Implementation | Evidence / limitation |
|---|---|---|
| Unicode normalization and hidden control removal | `normalize_question`; `normalize_extracted_text` | Unit and red-team tests; encoded natural-language attacks are not comprehensively decoded. |
| Direct injection detection | `HeuristicInjectionDetector`; block before retrieval/generation; security event metric | Pattern matching catches a small set of English/Swahili and Base64 cases; false negatives and false positives remain. No hosted classifier is wired. |
| Ingestion defense | Sanitization, chunk scanning, quarantine, provenance/trust metadata, content hashes | Suspicious chunks are ineligible until admin review. PDF rendering tricks such as white-on-white text and annotation layers are not reliably detected by text extraction. |
| Tenant boundary | Forced Postgres RLS and explicit repository filters; tenant-scoped cache and rate limits | Separate-tenant CI and database checks; retrieval must continue to be tested with deliberate filter omissions. |
| Prompt boundary | Random per-request delimiters; context data is explicitly untrusted; no tools | Prompt is versioned in `src/rag/prompts`; it contains no keys or tenant-specific policy. |
| Structured output and citations | Pydantic schema from Gemini adapter; retrieved chunk membership checked before response | Invalid/foreign citation IDs refuse the response. |
| Output handling | HTML, images, URLs and Markdown destinations stripped; sensitive-input action flag/redact/block; output secret/email and canary scan | Script and URL cases have deterministic tests. Pattern scanning does not identify all PII, secrets or policy violations. |
| Prompt leakage signal | Random service-instance canary added to system instruction; matching output is blocked and increments `rag_ai_canary_leaks_total` | A canary is a detection aid, not a proof that no prompt fragments leaked. |
| Generation kill switch | `GENERATION_ENABLED=false` skips model generation while preserving a safe refusal | Must be wired to an owner-controlled feature flag before production; current environment setting requires deploy/config change. |
| Provider tracing privacy | LangSmith client hides inputs/outputs; exporter queue only accepts allowlisted metadata; no prompt/document text or direct user IDs are sent | External export requires `LANGSMITH_TRACING=true` and a dedicated key. Region, retention, DPA and deletion terms remain owner gates. |
| Cost bounds | Per-request question/context/output limits, provider timeout/concurrency, API-key/tenant rate limits | Numeric spend quotas and provider spend caps are not set because owner budgets are open. Do not use production until set. |
| Security events | Structured events contain category/outcome, hashed tenant/key references and request ID; no raw content | Counters use bounded categories. Alert thresholds are operational defaults and require staging calibration. |

## Framework mapping

The mapping follows the OWASP Top 10 for LLM Applications 2025, MITRE ATLAS and the NIST AI RMF. These are planning and test-mapping frameworks; coverage does not imply compliance or risk elimination.

| OWASP LLM risk (2025) | Platform controls and red-team cases | MITRE ATLAS threat area | NIST AI RMF activity |
|---|---|---|---|
| LLM01 Prompt Injection | Input normalization, heuristic block, untrusted context delimiters, no tools, direct/indirect cases | LLM Prompt Injection; Initial Access | Map, Measure, Manage |
| LLM02 Sensitive Information Disclosure | PII/secret pattern handling, tenant RLS, metadata-only LangSmith traces, canary and output scan | Credential Access, Collection, Exfiltration | Govern, Map, Measure, Manage |
| LLM03 Supply Chain | Locked Python dependency set, pinned CI actions/images, provider ports, dependency audit | AI Supply Chain Compromise | Govern, Map, Manage |
| LLM04 Data and Model Poisoning | Chunk scanner, provenance/trust metadata, quarantine and reviewed release | Data Manipulation, Poisoning | Map, Measure, Manage |
| LLM05 Improper Output Handling | Strict JSON schema, citation checks, HTML/image/link stripping, no unsafe HTML rendering | Exfiltration, Impact | Map, Measure, Manage |
| LLM06 Excessive Agency | Fixed RAG pipeline, no model tools/network/write actions | LLM Prompt Injection; Impact | Govern, Map |
| LLM07 System Prompt Leakage | Non-sensitive prompt, canary scan, output refusal; extraction attempts in suite | LLM Prompt Injection; Exfiltration | Map, Measure, Manage |
| LLM08 Vector and Embedding Weaknesses | Tenant-filtered dense/FTS search, forced RLS, dimension validation, poisoning quarantine | Data Manipulation, Discovery | Map, Measure, Manage |
| LLM09 Misinformation | Source-only prompt, citation membership, insufficient-evidence refusal | LLM Prompt Injection; Impact | Map, Measure |
| LLM10 Unbounded Consumption | Request/context/token caps, timeout, concurrency, Redis rate limits, kill switch | Denial of ML Service | Govern, Map, Measure, Manage |

ATLAS is a living knowledge base, and its technique names evolve. This table maps threat classes and does not claim a one-to-one ATT&CK ID. NIST's Govern/Map/Measure/Manage activities are lifecycle responsibilities: owner governance and risk decisions, threat/context definition, adversarial/quality measurement, and mitigation/monitoring.

## Red-team execution

`make redteam` runs provider-free synthetic attack cases on each CI change. `tests/security/` covers direct injection, indirect poisoned text, Swahili, Base64, hidden Unicode, markup, image/link exfiltration, and canary handling. The current deterministic suite reports whether application controls blocked its known cases; it is not an LLM attack-success-rate benchmark. A full live-model/nightly campaign, jailbreak variation, cross-tenant end-to-end probe, cost abuse suite and category ASR report remain required before production.

The M5 zero-success targets for cross-tenant disclosure, secrets/prompt exfiltration and executable output are release gates, not claims made from this unit suite. Other category target is at most 5% after the owner approves the attack set and scoring method.

## Data sent to observability providers

LangSmith receives only allowlisted fields: request/trace correlation IDs, environment, model and prompt version, token counts, duration, outcome, and a one-way tenant pseudonym. Client-level input/output hiding is enabled. Grafana receives service metrics, route templates, status, durations and security counters. User questions, document text, user IDs, API keys, chunk text, filenames and tenant names are excluded. Prometheus labels are bounded to route/method/status or category/outcome; identifiers are never labels.

LangSmith endpoint/region, retention, contractual data protection, deletion API and tenant opt-out/sampling policy require owner confirmation. External tracing is disabled by default.

## Residual risks and release gates

- Heuristic injection detection can miss paraphrase, image/PDF visual tricks, non-English attacks and novel encodings.
- Query-time generation quality and groundedness are not independently verified by an NLI/judge in M5; that work is evaluated in M6.
- Daily spend quotas/provider spend cap need owner-set budgets. The kill switch is currently a deployment setting, not a remote, audited flag.
- Full LangSmith nested step traces, feedback export, sampling, tenant opt-out and deletion cascade are not yet implemented.
- Grafana Cloud contact points, synthetic canary, retention, missing-telemetry alerts, and cloud trace/log correlation need staging configuration.
- Public CI must retain secret scanning/push protection and pinned actions. No customer data or real API keys belong in fixtures.

## References checked 2026-11-16

- [OWASP Top 10 for Large Language Model Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [OWASP GenAI Security Project: 2025 risk list](https://genai.owasp.org/llm-top-10/)
- [MITRE ATLAS](https://atlas.mitre.org/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)

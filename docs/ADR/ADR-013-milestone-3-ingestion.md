# ADR-013: Bounded PDF ingestion and audited quarantine review

- Status: Proposed for owner confirmation at the Milestone 3 gate
- Date: 2026-11-16
- Context: Milestone 3 implements the approved PDF upload contract, asynchronous indexing, retries, deletion, and admin quarantine review. The owner has not selected an embedding model or dimension.

## Decision

- Accept PDF uploads only in this milestone, with a proposed 100 MiB upload limit, 250-page parser limit, and 32 MiB decompressed page-content guard. pypdf warns that content-stream parsing may require substantial memory; page content size is checked and oversized files fail with a stable error. Image-only PDFs fail as non-extractable text; OCR is out of scope.
- Store source files behind a BlobStore port. Local Compose uses a shared private volume. Production configuration requires a named private S3-compatible bucket and HTTPS endpoint. The S3 adapter uses boto3 managed transfers and explicit timeouts/retries; bucket-side encryption, access controls, lifecycle, and backups must be configured by infrastructure.
- Queue work through ARQ/Redis with stable job IDs and idempotent database writes. Delivery is at least once, so processing and deletion tolerate duplicate execution. Queue capacity defaults to 500 outstanding items per tenant and worker concurrency to two; both are proposed defaults.
- Extract page-aware text and use deterministic 2,400-character chunks with 300-character overlap. These are proposed defaults. A conservative heuristic scanner quarantines suspicious chunks; only non-quarantined chunks are embedded. Admin decisions require an admin API key, an idempotency key, and an audited reason.
- Use Gemini `gemini-embedding-2` with 768 dimensions as a proposed default pending owner confirmation. The adapter sends each input as a separate Content object to preserve one vector per chunk and validates response count and dimensions. No vector index is created until model/dimension approval and measured query plans.
- Local API and worker temporary filesystems use 256 MiB to accommodate a bounded 100 MiB upload/download plus parser overhead. Deployment must additionally cap request bodies at the reverse proxy and size worker memory against maximum PDF complexity.

## Consequences

- The current ingestion API accepts PDF only although broader formats are present in future-oriented requirements. This is an intentional milestone slice; DOCX/TXT/MD/HTML need a new implementation milestone and parser safety review.
- The scanner is a heuristic triage signal, not a safety guarantee. All retrieved text remains untrusted and future retrieval/generation must retain delimiters, output validation, citation checks, and no-tool model policy.
- pypdf's memory behavior can exceed the compressed file size; the content-stream guard and page limit reduce risk but do not provide a hard process memory limit. Container memory limits and hostile-PDF fault testing remain required.
- Gemini model retention, region, pricing, and service availability depend on account/tier and must be confirmed before production data is sent.
- Local disk storage is suitable only for development and loses durability with volume loss. Production must use private object storage with verified encryption and backup policy.
- Admin quarantine is implemented for API-key principals. BFF session support remains to be wired with the web milestone.

## Requirements

FR-ING-001..005, FR-ADM-001, NFR-PERF-002, NFR-SCALE-001/002, NFR-REL-001, NFR-SEC-001/003, NFR-AI-001/002, NFR-DATA-001.

## Official documentation checked

- [FastAPI request files / UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/) documents spooled temporary file behavior and async file operations.
- [pypdf text extraction](https://pypdf.readthedocs.io/en/latest/user/extract-text.html) documents text extraction limitations and large content-stream memory risk.
- [ARQ documentation](https://arq-docs.helpmanual.io/) documents async Redis-backed jobs, retries, and job IDs. [ARQ project metadata](https://github.com/python-arq/arq/blob/main/pyproject.toml) constrains the supported Redis client dependency; the project pins Redis below 6 accordingly.
- [Boto3 S3 upload_fileobj](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/bucket/upload_fileobj.html) and [S3 transfer configuration](https://docs.aws.amazon.com/boto3/latest/guide/s3.html) document managed multipart transfers and transfer configuration.
- [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings) documents the current `gemini-embedding-2` model, supported output dimensions (including recommended 768), input limits, separate Content inputs, and incompatibility with the older embedding model space.
- [MinIO container deployment](https://min.io/docs/minio/container/index.html) was checked. Compose keeps local disk as the default and does not add a single-node MinIO service; production object storage is an external deployment dependency.

## Open questions

1. Confirm or replace `gemini-embedding-2` and 768 dimensions, including the account's region, retention terms, and cost limit.
2. Confirm upload/page/chunk/queue/concurrency defaults against expected tenant volumes and memory budgets.
3. Choose and verify the production S3-compatible provider, encryption, retention, backup, and deletion policy.
4. Confirm whether image-only PDF OCR is required for the first release.
5. Confirm whether admin review will use API keys, web sessions, or both after the BFF milestone.

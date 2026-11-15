# ADR-005: Private blob storage and bounded PDF uploads

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

Raw PDFs are larger than appropriate for a database row and must be deleted independently with derived chunks. BRIEF requires an S3-compatible abstraction and warns Render service disks are not shared between services.

## Decision

Define a BlobStore port with an S3-compatible production implementation and local disk implementation for development only. V1 accepts one non-resumable PDF per multipart request, streams to private storage with a configurable hard byte limit, validates content type/signature, invokes a malware-scan hook, and returns an idempotent job. Object-store vendor, maximum size/pages, OCR and retention remain open.

## Evidence checked

- Render [service types documentation](https://render.com/docs/service-types) describes persistent disks as attached to individual services; the design therefore does not assume that a worker and web service share such a disk.
- This is a data lifecycle/design decision; the final object store's multipart, encryption, lifecycle and deletion guarantees need official provider verification before implementation.

## Consequences

- Worker and API can independently access durable source objects.
- Adds external storage credentials and deletion/backup responsibilities.
- Whole-upload retries can be expensive; resumable uploads can be added only if owner and measured size needs justify them.


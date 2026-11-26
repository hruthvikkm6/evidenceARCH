# Architecture

## Local application

```text
React + Vite ──same-origin /api proxy──> FastAPI v1
                                          ├── Auth service: Argon2 + HttpOnly JWT cookie
                                          ├── SQLite: users, cases, evidence and audit data
                                          ├── Acquisition service: validation, SHA-256, originals
                                          └── Module adapters: Registry parser, graph, investigation, verifier
```

The Vite development server proxies `/api` to FastAPI. No hosted service or API key is needed. SQLite and acquired evidence live under the configured local backend data directory.

## Separation of responsibilities

- API routes validate requests, enforce the local user/case boundary, call services and return structured responses.
- Pydantic schemas describe authentication, case, evidence, claim and gap contracts.
- SQLite initialization creates tables and adds nullable/defaulted columns to earlier local databases without deleting records.
- Acquisition classifies and validates file signatures, hashes content while streaming to a temporary file, then moves the unchanged bytes into hash-addressed original storage. Only Registry inputs get a separate working copy.
- Adapters define stable boundaries. Current parser and investigator adapters are demos; the graph adapter draws only synthetic source-file-to-record provenance links for `DEMO_ONLY` records and omits real evidence; the unconfigured verifier conservatively returns `NOT_ESTABLISHED`.

## Authentication

Signup hashes passwords with Argon2. Login returns the user profile and sets a short-lived JWT in an HttpOnly, SameSite cookie scoped to `/api`. Browser JavaScript cannot read the token. APIs that expose case data require an active user and scope cases to their investigator ID. If `EVIDENCEARCH_JWT_SECRET` is not set, a random process-local secret is used, so sessions expire when the backend restarts. Local HTTP development defaults the cookie `Secure` flag off; local HTTPS deployments should set it on.

## Evidence lifecycle

```text
Upload -> extension/signature validation -> SHA-256 -> original preserved -> acquisition log
                                            ├── Registry: working copy -> Member 2 parser
                                            └── Supplement: retained metadata -> future document tools
```

Case deletion archives the case. Evidence withdrawal hides a file from active views but retains the original, normalized records, and audit history. These behaviors protect provenance while allowing investigators to close or remove items from their active workspace.

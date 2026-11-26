# API contract

Base path: `/api/v1`. JSON errors use FastAPI's `detail` field. Signup and login are public; case/evidence/investigation endpoints require the `evidencearch_session` HttpOnly cookie. The React dev server proxies `/api` to FastAPI, so browser requests are same-origin.

## Authentication

- `POST /auth/signup` — `{ "full_name":"Investigator", "email":"name@example.com", "password":"10+ characters" }`; creates `INVESTIGATOR` and signs in.
- `POST /auth/login` — `{ "email":"name@example.com", "password":"..." }`; sets the session cookie.
- `POST /auth/logout` — clears the cookie.
- `GET /auth/me` — current public user fields.

Passwords are Argon2-hashed. Signup returns `409` for duplicate email; login returns a generic `401` for incorrect credentials. Account role defaults to `INVESTIGATOR`.

## Cases

- `GET /cases` — cases owned by the signed-in investigator, with evidence/investigation counts.
- `POST /cases` — `{ "name":"Lab case", "description":"", "status":"OPEN" }`.
- `GET /cases/{case_id}`
- `PATCH /cases/{case_id}` or `PUT /cases/{case_id}` — update name, description or status (`OPEN`, `IN_PROGRESS`, `CLOSED`, `ARCHIVED`).
- `DELETE /cases/{case_id}` — archives; does not erase evidence.

## Evidence and acquisition

- `POST /cases/{case_id}/evidence/upload` — multipart form field `file`.
- `GET /cases/{case_id}/evidence` — active case files.
- `GET /evidence/{evidence_id}` — file metadata, extracted records and metadata map.
- `GET /evidence/{evidence_id}/open` — serves the preserved original read-only; supported text, PDF and image types render inline; binary/Word files download.
- `GET /evidence/{evidence_id}/acquisition` — file acquisition data and audit log.
- `DELETE /evidence/{evidence_id}` — withdraws from active views; original bytes remain stored.
- `GET /cases/{case_id}/acquisition-log`

Responses include original filename, category, file size, SHA-256, UTC acquisition time, uploaded-by ID, validation status and processing status. Registry files get a working copy; supplementary evidence is not passed to the Registry parser.

Accepted extensions: Registry `.dat`, `.hive`, `.bin`, `.reg`; supplementary `.pdf`, `.docx`, `.txt`, `.csv`, `.json`, `.xml`, `.jpg`, `.jpeg`, `.png`, `.webp`, `.evtx`, `.log`. Maximum upload size is configured by `EVIDENCEARCH_MAX_UPLOAD_BYTES`.

## Parser, graph, investigation and verification

- `POST /cases/{case_id}/parse?evidence_id=...`
- `GET /cases/{case_id}/records`
- `GET /cases/{case_id}/graph`
- `POST /cases/{case_id}/investigate` — `{ "question":"What evidence is available?" }`
- `GET /cases/{case_id}/investigations`
- `GET /investigations/{investigation_id}/claims`
- `POST /cases/{case_id}/verify` — `{ "claims":[...] }`
- `GET /claims/{claim_id}/verification`
- `GET /cases/{case_id}/verifications`
- `POST /cases/{case_id}/demo/seed` — adds repository-controlled synthetic `.dat`, `.reg`, and `.txt` fixtures, clearly marked as demo evidence.
- `GET /health`

The investigation adapter may propose claims and gaps. Only the verifier assigns `SUPPORTED`, `CONTRADICTED` or `NOT_ESTABLISHED`. Gap categories are `NOT_COLLECTED`, `UNAVAILABLE`, `EXPECTED_BUT_NOT_FOUND`, and `MAY_NEVER_HAVE_EXISTED`.

Swagger UI: `/docs`; OpenAPI JSON: `/openapi.json`.

# EvidenceARCH Phase 1 Integration Contracts

Base URL: `http://127.0.0.1:8000/api/v1`. JSON is UTF-8. Errors use `{"detail":"..."}`. Interactive OpenAPI: `/docs`.

Case and evidence APIs require an authenticated investigator session. Sign up or log in through `/auth/signup` or `/auth/login`; the JWT is sent in an HttpOnly cookie. The local Vite proxy keeps browser API calls same-origin.

## Common evidence record

```json
{
  "evidence_id":"uuid",
  "case_id":"uuid",
  "artifact_type":"USBSTOR_DEVICE",
  "source_file":"SYSTEM",
  "source_path":"ControlSet001\\Enum\\USBSTOR\\...",
  "extracted_data":{"vendor":"..."},
  "event_timestamp":"2026-01-01T00:00:00Z",
  "timestamp_type":"Registry key last-write time",
  "user_identifier":null,
  "device_identifier":"...",
  "file_hash":null,
  "parser_version":"member2/0.1",
  "validation_status":"VALIDATED",
  "source_evidence_id":"uploaded-file-uuid"
}
```

`source_evidence_id` is the source upload FK and is required by the persistence boundary. `evidence_id` may be omitted for server UUID assignment. Keep timestamps timezone-aware when known; never synthesize event times. Artifact-specific values belong in `extracted_data`.

## Member 2: Registry parser

Replace `DemoParser` with an object implementing `parse(case_id, file_id, source_file, working_copy_path) -> list[dict]`. The backend passes the working copy path, original source filename, case ID, and upload ID. Return normalized records above; raise typed errors for corrupt/unsupported hive inputs. The backend persists each record and links it to the source upload. Do not mutate the original.

## Member 3: graph and verifier

Graph: implement `get_graph(case_id, records) -> {case_id, nodes, edges, ...}`. Return nodes as Cytoscape-compatible objects with a top-level `id` and optional `label`, `kind`, and provenance fields. Return edges with `id`, `source`, `target`, `relationship_type`, `rule`, `supporting_evidence_ids`, and `explanation`. Example: `{"case_id":"...","nodes":[{"id":"record-1","label":"USBSTOR record","kind":"evidence","evidence_id":"record-1"}],"edges":[{"id":"edge-1","source":"record-1","target":"device-1","relationship_type":"same_device_identifier","rule":"R1","supporting_evidence_ids":["record-1"],"explanation":"Both records contain the same device identifier."}]}`. The UI displays selected node/edge data, including the rule and explanation. The default demo graph creates only explicit synthetic file-to-record provenance links for `DEMO_ONLY` records; it never fabricates relationships for real evidence. Empty graph is valid; do not infer relationships without a documented rule.

Verifier: implement `verify(claim, records) -> Claim`. Validate cited evidence IDs; assign only `SUPPORTED`, `CONTRADICTED`, or `NOT_ESTABLISHED`, with a concise explanation and traceable supporting/conflicting IDs where practical. The investigation adapter proposes claims but never determines status.

## Member 4: investigation/RAG

Implement `investigate(question, records, graph, supplementary_files) -> {claims, uncertainty, recommendations, evidence_gaps}`. Supplementary file entries include only evidence ID, original filename, category, SHA-256 and validation status. Claims follow `{claim_id, claim_text, evidence_ids, reasoning}`; status fields are assigned after the result is passed to Member 3's verifier. Distinguish observed records from hypotheses, expose uncertainty and recommendations, cite only real case evidence IDs, and disclose demo mode. Evidence gaps use `category`, `explanation`, `why_it_matters`, and `recommended_next_step`; categories are `NOT_COLLECTED`, `UNAVAILABLE`, `EXPECTED_BUT_NOT_FOUND`, and `MAY_NEVER_HAVE_EXISTED`. Local/offline models are optional; no API key is needed by Member 1.

## Endpoints

- `GET /health`
- `POST /cases`, `GET /cases`, `GET /cases/{case_id}`, `PATCH /cases/{case_id}`
- `POST /cases/{case_id}/evidence/upload` multipart field `file`
- `GET /cases/{case_id}/evidence`, `GET /evidence/{evidence_id}`, `GET /evidence/{evidence_id}/open` (read-only original file)
- `GET /evidence/{evidence_id}/acquisition`, `DELETE /evidence/{evidence_id}` (withdraws from active views but preserves original)
- `GET /cases/{case_id}/acquisition-log`
- `POST /cases/{case_id}/parse?evidence_id=...`, `GET /cases/{case_id}/records`
- `GET /cases/{case_id}/graph`
- `POST /cases/{case_id}/investigate` body `{"question":"..."}`; `GET /cases/{case_id}/investigations`
- `POST /cases/{case_id}/verify` body `{"claims":[...]}`; `GET /cases/{case_id}/verifications`
- `POST /cases/{case_id}/demo/seed` explicit synthetic fixture only, when demo mode is enabled.
- Authentication: `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.

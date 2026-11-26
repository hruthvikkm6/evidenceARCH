# Integration guide for Members 2–4

The local FastAPI backend is the integration boundary. Replacing an adapter should not require changing the React views or acquisition database tables. Detailed route signatures and payload examples are in `INTEGRATION.md` and `api-contract.md`.

## Member 2 — Registry parser

Implement `RegistryParserAdapter.parse(case_id, file_id, source_file, working_copy_path) -> list[dict]`. It is called only for `REGISTRY_HIVE` and `REGISTRY_EXPORT`. The path is a separate working copy. Return the common evidence schema, including `artifact_type`, `source_file`, `source_path`, `extracted_data`, timestamp semantics, parser version, validation status and `source_evidence_id`. The API validates each record with Pydantic and links it back to the uploaded file. Never modify the original.

## Member 3 — graph and verifier

Implement `EvidenceGraphAdapter.get_graph(case_id, records) -> {case_id,nodes,edges,...}`. Keep identifiers, documented rules, supporting evidence IDs and explanations in returned elements. Empty graphs are valid. The demo adapter shows only synthetic source-file-to-record provenance links for `DEMO_ONLY` records; it excludes real records and labels all output as demo.

Implement `VerificationAdapter.verify(claim, records) -> Claim`. Resolve evidence IDs and assign exactly one supported status with an explanation. The API overwrites any proposed status by passing the claim through this adapter.

## Member 4 — investigation/RAG

Implement `RAGInvestigationAdapter.investigate(question, records, graph, supplementary_files)`. Supplementary file entries include evidence ID, original filename, category, SHA-256, and validation status, but no server path. The adapter can return claims (without final status), uncertainty, recommendations and typed evidence gaps. Do not claim PDF/image text extraction until it exists. Any optional local model must remain optional; no external key is required for the base app.

## Wiring

Adapter instances are currently created in `backend/app/api/routes.py` (`parser`, `graph_adapter`, `investigator`, `verifier`). Inject the real implementations there or through a small factory. Keep the provided demo implementations for offline development and tests.

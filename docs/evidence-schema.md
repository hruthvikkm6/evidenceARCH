# Evidence and claim schemas

## Evidence record

Registry parser records must preserve the shared schema. `source_evidence_id` is the uploaded file ID used to enforce provenance in storage.

```json
{
  "evidence_id":"server UUID or parser UUID",
  "case_id":"case UUID",
  "artifact_type":"USBSTOR_DEVICE",
  "source_file":"SYSTEM",
  "source_path":"ControlSet001\\Enum\\USBSTOR\\...",
  "extracted_data":{"device_identifier":"..."},
  "event_timestamp":null,
  "timestamp_type":null,
  "user_identifier":null,
  "device_identifier":"...",
  "file_hash":null,
  "parser_version":"member2/0.1",
  "validation_status":"VALIDATED",
  "source_evidence_id":"uploaded-file UUID"
}
```

## Uploaded file category

`REGISTRY_HIVE`, `REGISTRY_EXPORT`, `DOCUMENT`, `IMAGE`, `OTHER_FORENSIC_EVIDENCE`, `DEMO`, or `LEGACY_UNCLASSIFIED`. The latter two indicate demo/older data and should not be treated as validated Registry artifacts.

## Claim

```json
{
  "claim_id":"uuid",
  "claim_text":"Proposed statement",
  "evidence_ids":["evidence record UUID"],
  "reasoning":"Why the investigation adapter proposed it",
  "verification_status":"NOT_ESTABLISHED",
  "verification_explanation":"Assigned by the independent verifier"
}
```

Supported statuses are exactly `SUPPORTED`, `CONTRADICTED`, and `NOT_ESTABLISHED`. Investigation adapters propose the text and evidence IDs; they must not decide the final status.

## Evidence gap

Each gap has `category`, `explanation`, `why_it_matters`, and `recommended_next_step`. Categories use `NOT_COLLECTED`, `UNAVAILABLE`, `EXPECTED_BUT_NOT_FOUND`, and `MAY_NEVER_HAVE_EXISTED`. A gap is a case hypothesis until supported by the relevant collection/availability facts; demo output is marked as such.

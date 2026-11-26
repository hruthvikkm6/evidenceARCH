import json, uuid
from datetime import datetime, timezone
from app.db.database import db_session

def now(): return datetime.now(timezone.utc).isoformat()
def records(case_id):
    with db_session() as db:
        return [dict(r) | {"extracted_data":json.loads(r["extracted_data"])} for r in db.execute("SELECT * FROM evidence_records WHERE case_id=? ORDER BY created_at",(case_id,))]
def save_record(case_id, file_id, record):
    rid=record.get("evidence_id") or str(uuid.uuid4()); created=now()
    with db_session() as db:
        if not db.execute("SELECT 1 FROM evidence_files WHERE evidence_id=? AND case_id=?",(file_id,case_id)).fetchone(): raise ValueError("source evidence file does not belong to this case")
        db.execute("INSERT INTO evidence_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,case_id,file_id,record["artifact_type"],record["source_file"],record["source_path"],json.dumps(record["extracted_data"]),record.get("event_timestamp"),record.get("timestamp_type"),record.get("user_identifier"),record.get("device_identifier"),record.get("file_hash"),record["parser_version"],record["validation_status"],created))
    return rid

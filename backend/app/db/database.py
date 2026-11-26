import sqlite3, uuid
from contextlib import contextmanager
from app.core.config import settings

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'INVESTIGATOR', is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cases(case_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, case_number TEXT UNIQUE, investigator_id TEXT REFERENCES users(user_id) ON DELETE SET NULL, status TEXT NOT NULL DEFAULT 'OPEN');
CREATE TABLE IF NOT EXISTS evidence_files(evidence_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE, original_filename TEXT NOT NULL, stored_filename TEXT NOT NULL, file_path TEXT NOT NULL, working_copy_path TEXT NOT NULL, file_size INTEGER NOT NULL, sha256 TEXT NOT NULL, acquired_at TEXT NOT NULL, media_type TEXT, is_demo INTEGER NOT NULL DEFAULT 0, category TEXT NOT NULL DEFAULT 'LEGACY_UNCLASSIFIED', validation_status TEXT NOT NULL DEFAULT 'UNVERIFIED_LEGACY', uploaded_by TEXT REFERENCES users(user_id) ON DELETE SET NULL, is_withdrawn INTEGER NOT NULL DEFAULT 0, UNIQUE(case_id,sha256));
CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence_files(case_id);
CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence_files(sha256);
CREATE TABLE IF NOT EXISTS evidence_records(evidence_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE, file_id TEXT NOT NULL REFERENCES evidence_files(evidence_id) ON DELETE RESTRICT, artifact_type TEXT NOT NULL, source_file TEXT NOT NULL, source_path TEXT NOT NULL, extracted_data TEXT NOT NULL, event_timestamp TEXT, timestamp_type TEXT, user_identifier TEXT, device_identifier TEXT, file_hash TEXT, parser_version TEXT NOT NULL, validation_status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_records_case ON evidence_records(case_id);
CREATE INDEX IF NOT EXISTS idx_records_artifact ON evidence_records(artifact_type);
CREATE INDEX IF NOT EXISTS idx_records_user ON evidence_records(user_identifier);
CREATE INDEX IF NOT EXISTS idx_records_device ON evidence_records(device_identifier);
CREATE INDEX IF NOT EXISTS idx_records_time ON evidence_records(event_timestamp);
CREATE TABLE IF NOT EXISTS evidence_metadata(metadata_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence_files(evidence_id) ON DELETE CASCADE, key TEXT NOT NULL, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS investigation_results(investigation_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE, question TEXT NOT NULL, result_json TEXT NOT NULL, adapter TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims(claim_id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL REFERENCES investigation_results(investigation_id) ON DELETE CASCADE, case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE, claim_text TEXT NOT NULL, evidence_ids_json TEXT NOT NULL, reasoning TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS verification_results(verification_id TEXT PRIMARY KEY, investigation_id TEXT REFERENCES investigation_results(investigation_id) ON DELETE CASCADE, case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE, claim_id TEXT NOT NULL, claim_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_verifications_case ON verification_results(case_id);
CREATE TABLE IF NOT EXISTS acquisition_logs(log_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE, evidence_id TEXT NOT NULL REFERENCES evidence_files(evidence_id) ON DELETE CASCADE, action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
"""

MIGRATIONS = {
    "cases": [
        ("case_number", "TEXT"),
        ("investigator_id", "TEXT REFERENCES users(user_id) ON DELETE SET NULL"),
        ("status", "TEXT NOT NULL DEFAULT 'OPEN'"),
    ],
    "evidence_files": [
        ("category", "TEXT NOT NULL DEFAULT 'LEGACY_UNCLASSIFIED'"),
        ("validation_status", "TEXT NOT NULL DEFAULT 'UNVERIFIED_LEGACY'"),
        ("uploaded_by", "TEXT REFERENCES users(user_id) ON DELETE SET NULL"),
        ("is_withdrawn", "INTEGER NOT NULL DEFAULT 0"),
    ],
}

def connect():
    conn=sqlite3.connect(settings.database_path, timeout=15)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    settings.prepare()
    db=connect()
    try:
        db.executescript(SCHEMA)
        for table,columns in MIGRATIONS.items():
            existing={row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for name,definition in columns:
                if name not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_number ON cases(case_number)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_cases_investigator ON cases(investigator_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_files_uploader ON evidence_files(uploaded_by)")
        for row in db.execute("SELECT case_id FROM cases WHERE case_number IS NULL OR case_number='' ").fetchall():
            db.execute("UPDATE cases SET case_number=? WHERE case_id=?",("CASE-LEGACY-"+row["case_id"][:8].upper(),row["case_id"]))
    finally: db.close()

@contextmanager
def db_session():
    db=connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback(); raise
    finally: db.close()

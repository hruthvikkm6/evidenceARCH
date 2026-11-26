import io, json, sqlite3, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pathlib import Path
import mimetypes
from starlette.datastructures import Headers
from app.db.database import db_session
from app.schemas.contracts import CaseCreate, CaseUpdate, CaseOut, InvestigationRequest, InvestigationResult, VerifyRequest, Claim, EvidenceRecordIn
from app.services.acquisition import acquire_upload
from app.services.repository import records, save_record, now
from app.integrations.adapters import DemoParser, DemoGraph, DemoInvestigator, UnconfiguredVerifier
from app.core.security import get_current_user

public_router=APIRouter(prefix="/api/v1",tags=["health"])
router=APIRouter(prefix="/api/v1",tags=["cases","evidence","investigation"],dependencies=[Depends(get_current_user)])
parser=DemoParser(); graph_adapter=DemoGraph(); investigator=DemoInvestigator(); verifier=UnconfiguredVerifier()

def case_or_404(db,case_id,user):
    row=db.execute("SELECT * FROM cases WHERE case_id=? AND investigator_id=?",(case_id,user["user_id"])).fetchone()
    if row is None: raise HTTPException(404,"Case not found.")
    return row

def case_view(db,row):
    result=dict(row)
    result["evidence_count"]=db.execute("SELECT count(*) FROM evidence_files WHERE case_id=? AND is_withdrawn=0",(row["case_id"],)).fetchone()[0]
    result["investigation_count"]=db.execute("SELECT count(*) FROM investigation_results WHERE case_id=?",(row["case_id"],)).fetchone()[0]
    return result

@public_router.get("/health")
def health(): return {"status":"ok","service":"evidenceARCH-api","api_version":"v1"}

@router.post("/cases",response_model=CaseOut,status_code=201)
def create_case(body:CaseCreate,user=Depends(get_current_user)):
    cid=str(uuid.uuid4()); timestamp=now(); year=datetime.now(timezone.utc).year
    with db_session() as db:
        serial=db.execute("SELECT count(*) FROM cases WHERE case_number LIKE ?",(f"CASE-{year}-%",)).fetchone()[0]+1
        case_number=f"CASE-{year}-{serial:03d}"
        db.execute("INSERT INTO cases(case_id,name,description,created_at,updated_at,case_number,investigator_id,status) VALUES(?,?,?,?,?,?,?,?)",(cid,body.name,body.description,timestamp,timestamp,case_number,user["user_id"],body.status))
        row=db.execute("SELECT * FROM cases WHERE case_id=?",(cid,)).fetchone()
        return case_view(db,row)

@router.get("/cases")
def list_cases(user=Depends(get_current_user)):
    with db_session() as db:
        rows=db.execute("SELECT * FROM cases WHERE investigator_id=? ORDER BY created_at DESC",(user["user_id"],)).fetchall()
        return [case_view(db,row) for row in rows]

@router.get("/cases/{case_id}",response_model=CaseOut)
def get_case(case_id:str,user=Depends(get_current_user)):
    with db_session() as db: return case_view(db,case_or_404(db,case_id,user))

@router.patch("/cases/{case_id}",response_model=CaseOut)
@router.put("/cases/{case_id}",response_model=CaseOut)
def update_case(case_id:str,body:CaseUpdate,user=Depends(get_current_user)):
    patch=body.model_dump(exclude_unset=True)
    with db_session() as db:
        case_or_404(db,case_id,user)
        if patch:
            db.execute("UPDATE cases SET name=COALESCE(?,name),description=COALESCE(?,description),status=COALESCE(?,status),updated_at=? WHERE case_id=?",(patch.get("name"),patch.get("description"),patch.get("status"),now(),case_id))
        return case_view(db,case_or_404(db,case_id,user))

@router.delete("/cases/{case_id}")
def archive_case(case_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        db.execute("UPDATE cases SET status='ARCHIVED',updated_at=? WHERE case_id=?",(now(),case_id))
    return {"case_id":case_id,"status":"ARCHIVED","message":"Case archived; evidence and audit history remain preserved."}

@router.post("/cases/{case_id}/evidence/upload",status_code=201)
async def upload(case_id:str,file:UploadFile=File(...),user=Depends(get_current_user)):
    with db_session() as db: case_or_404(db,case_id,user)
    result,duplicate=await acquire_upload(case_id,file,user["user_id"])
    result["duplicate"]=duplicate
    result["demo"]=bool(result.get("is_demo"))
    result["processing_status"]="READY_FOR_REGISTRY_PARSER" if result["category"] in {"REGISTRY_HIVE","REGISTRY_EXPORT"} else "STORED_AS_SUPPLEMENTARY_EVIDENCE"
    result["preservation"]="Original preserved; Registry parsing uses a working copy." if result["working_copy_path"] else "Original preserved; no Registry parsing is performed for this supplementary file."
    return result

@router.get("/cases/{case_id}/evidence")
def list_evidence(case_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        return [dict(r) for r in db.execute("SELECT * FROM evidence_files WHERE case_id=? AND is_withdrawn=0 ORDER BY acquired_at DESC",(case_id,))]

@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        f=db.execute("SELECT * FROM evidence_files WHERE evidence_id=? AND is_withdrawn=0",(evidence_id,)).fetchone()
        if not f: raise HTTPException(404,"Evidence file not found.")
        case_or_404(db,f["case_id"],user)
        rs=[dict(r)|{"extracted_data":json.loads(r["extracted_data"])} for r in db.execute("SELECT * FROM evidence_records WHERE file_id=?",(evidence_id,))]
        metadata=[dict(r) for r in db.execute("SELECT key,value FROM evidence_metadata WHERE evidence_id=?",(evidence_id,))]
        return {**dict(f),"metadata":metadata,"records":rs}

@router.get("/evidence/{evidence_id}/open")
def open_evidence_original(evidence_id:str,user=Depends(get_current_user)):
    """Serve the preserved original read-only; supported documents render inline."""
    with db_session() as db:
        f=db.execute("SELECT * FROM evidence_files WHERE evidence_id=? AND is_withdrawn=0",(evidence_id,)).fetchone()
        if not f: raise HTTPException(404,"Evidence file not found.")
        case_or_404(db,f["case_id"],user)
        original=Path(f["file_path"])
        if not original.is_file(): raise HTTPException(404,"Original evidence file is unavailable.")
        suffix=original.suffix.lower()
        media_type=mimetypes.guess_type(f["original_filename"])[0] or f["media_type"] or "application/octet-stream"
        inline=suffix in {".pdf",".reg",".txt",".csv",".json",".xml",".jpg",".jpeg",".png",".webp",".log"}
        return FileResponse(
            original,
            media_type=media_type,
            filename=f["original_filename"],
            content_disposition_type="inline" if inline else "attachment",
            headers={"X-Content-Type-Options":"nosniff","Cache-Control":"no-store"},
        )

@router.get("/evidence/{evidence_id}/acquisition")
def evidence_acquisition(evidence_id:str,user=Depends(get_current_user)):
    detail=get_evidence(evidence_id,user)
    with db_session() as db: log=[dict(r) for r in db.execute("SELECT * FROM acquisition_logs WHERE evidence_id=? ORDER BY created_at",(evidence_id,))]
    return {"evidence_id":evidence_id,"acquisition":detail,"audit_log":log}

@router.delete("/evidence/{evidence_id}")
def withdraw_evidence(evidence_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        f=db.execute("SELECT * FROM evidence_files WHERE evidence_id=? AND is_withdrawn=0",(evidence_id,)).fetchone()
        if not f: raise HTTPException(404,"Evidence file not found.")
        case_or_404(db,f["case_id"],user)
        timestamp=now()
        db.execute("UPDATE evidence_files SET is_withdrawn=1 WHERE evidence_id=?",(evidence_id,))
        db.execute("INSERT INTO acquisition_logs VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),f["case_id"],evidence_id,"WITHDRAWN_FROM_ACTIVE_CASE","Hidden from active evidence views; original bytes and provenance retained.",timestamp))
    return {"evidence_id":evidence_id,"withdrawn":True,"message":"Evidence is hidden from active views. Original file and audit history remain preserved."}

@router.get("/cases/{case_id}/acquisition-log")
def acquisition_log(case_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        return [dict(r) for r in db.execute("SELECT * FROM acquisition_logs WHERE case_id=? ORDER BY created_at DESC",(case_id,))]

@router.post("/cases/{case_id}/parse")
def parse(case_id:str,evidence_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        f=db.execute("SELECT * FROM evidence_files WHERE evidence_id=? AND case_id=? AND is_withdrawn=0",(evidence_id,case_id)).fetchone()
        if not f: raise HTTPException(404,"Evidence file not found in this case.")
        if f["category"] not in {"REGISTRY_HIVE","REGISTRY_EXPORT"}: raise HTTPException(415,"Supplementary documents and images are not sent to the Registry parser.")
    try: output=parser.parse(case_id=case_id,file_id=evidence_id,source_file=f["original_filename"],working_copy_path=f["working_copy_path"])
    except Exception as exc: raise HTTPException(503,"Parser adapter is unavailable.") from exc
    saved=[]
    for rec in output:
        try:
            validated=EvidenceRecordIn(**{**rec,"case_id":case_id,"source_evidence_id":rec.get("source_evidence_id",evidence_id)})
            if validated.source_evidence_id!=evidence_id: raise ValueError("parser returned a different source id")
            normalized=validated.model_dump(mode="json",exclude={"source_evidence_id"})
            rid=save_record(case_id,evidence_id,normalized); saved.append({**normalized,"evidence_id":rid,"case_id":case_id})
        except Exception as exc: raise HTTPException(502,"Parser returned an invalid evidence record.") from exc
    return {"case_id":case_id,"file_id":evidence_id,"records":saved,"adapter":parser.name,"is_demo":parser.name.startswith("demo")}

@router.get("/cases/{case_id}/records")
def list_records(case_id:str,user=Depends(get_current_user)):
    with db_session() as db: case_or_404(db,case_id,user)
    return records(case_id)

@router.get("/cases/{case_id}/graph")
def get_graph(case_id:str,user=Depends(get_current_user)):
    with db_session() as db: case_or_404(db,case_id,user)
    try: return graph_adapter.get_graph(case_id=case_id,records=records(case_id))
    except Exception as exc: raise HTTPException(503,"Graph service is unavailable.") from exc

@router.post("/cases/{case_id}/investigate")
def investigate(case_id:str,body:InvestigationRequest,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        files=[dict(r) for r in db.execute("SELECT evidence_id,original_filename,category,sha256,validation_status FROM evidence_files WHERE case_id=? AND is_withdrawn=0",(case_id,))]
    try:
        case_records=records(case_id)
        result=investigator.investigate(question=body.question,records=case_records,graph=graph_adapter.get_graph(case_id=case_id,records=case_records),supplementary_files=files)
        iid=str(uuid.uuid4()); claims=[]
        for item in result.get("claims",[]):
            claim=verifier.verify(claim=Claim(**item),records=case_records); claims.append(claim.model_dump(mode="json"))
        response=InvestigationResult(investigation_id=iid,question=body.question,claims=claims,uncertainty=result.get("uncertainty",[]),recommendations=result.get("recommendations",[]),evidence_gaps=result.get("evidence_gaps",[]),adapter=investigator.name,is_demo=investigator.name.startswith("demo")).model_dump(mode="json")
        with db_session() as db:
            db.execute("INSERT INTO investigation_results VALUES(?,?,?,?,?,?)",(iid,case_id,body.question,json.dumps(response),investigator.name,now()))
            for claim in claims:
                db.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?)",(claim["claim_id"],iid,case_id,claim["claim_text"],json.dumps(claim["evidence_ids"]),claim["reasoning"],now()))
                db.execute("INSERT INTO verification_results VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),iid,case_id,claim["claim_id"],json.dumps(claim),now()))
        return response
    except Exception as exc: raise HTTPException(503,"Investigation or verification adapter is unavailable.") from exc

@router.get("/cases/{case_id}/investigations")
def list_investigations(case_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        return [{**dict(r),"result":json.loads(r["result_json"])} for r in db.execute("SELECT * FROM investigation_results WHERE case_id=? ORDER BY created_at DESC",(case_id,))]

@router.get("/investigations/{investigation_id}/claims")
def investigation_claims(investigation_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        investigation=db.execute("SELECT * FROM investigation_results WHERE investigation_id=?",(investigation_id,)).fetchone()
        if not investigation: raise HTTPException(404,"Investigation not found.")
        case_or_404(db,investigation["case_id"],user)
        return [dict(r)|{"evidence_ids":json.loads(r["evidence_ids_json"])} for r in db.execute("SELECT * FROM claims WHERE investigation_id=?",(investigation_id,))]

@router.get("/claims/{claim_id}/verification")
def claim_verification(claim_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        result=db.execute("SELECT * FROM verification_results WHERE claim_id=? ORDER BY created_at DESC LIMIT 1",(claim_id,)).fetchone()
        if not result: raise HTTPException(404,"Verification result not found.")
        case_or_404(db,result["case_id"],user)
        return json.loads(result["claim_json"])

@router.post("/cases/{case_id}/verify")
def verify(case_id:str,body:VerifyRequest,user=Depends(get_current_user)):
    with db_session() as db: case_or_404(db,case_id,user)
    try: return {"case_id":case_id,"claims":[verifier.verify(claim=c,records=records(case_id)).model_dump(mode="json") for c in body.claims],"adapter":verifier.name}
    except Exception as exc: raise HTTPException(503,"Verification service is unavailable.") from exc

@router.get("/cases/{case_id}/verifications")
def list_verifications(case_id:str,user=Depends(get_current_user)):
    with db_session() as db:
        case_or_404(db,case_id,user)
        return [{**dict(r),"claim":json.loads(r["claim_json"])} for r in db.execute("SELECT * FROM verification_results WHERE case_id=? ORDER BY created_at DESC",(case_id,))]

@router.post("/cases/{case_id}/demo/seed",status_code=201)
async def seed_demo(case_id:str,user=Depends(get_current_user)):
    from app.core.config import settings
    if not settings.demo_mode: raise HTTPException(403,"Demo mode is disabled.")
    with db_session() as db:
        case_or_404(db,case_id,user)
    demo_dir=Path(__file__).resolve().parents[3]/"demo"
    fixtures=[
        ("synthetic_registry_header_only.dat","application/octet-stream"),
        ("synthetic_registry_export.reg","text/plain"),
        ("synthetic_context.txt","text/plain"),
    ]
    acquired=[]
    for filename,media_type in fixtures:
        path=demo_dir/filename
        if not path.is_file(): raise HTTPException(503,"Controlled demo sample files are unavailable.")
        sample=UploadFile(filename=filename,file=io.BytesIO(path.read_bytes()),headers=Headers({"content-type":media_type}))
        result,duplicate=await acquire_upload(case_id,sample,user["user_id"],is_demo=True)
        acquired.append({"evidence_id":result["evidence_id"],"filename":filename,"category":result["category"],"sha256":result["sha256"],"duplicate":duplicate,"demo":True})
    return {"case_id":case_id,"evidence":acquired,"demo":True,"message":"Synthetic sample files added. They contain no real user, device, or Registry evidence."}

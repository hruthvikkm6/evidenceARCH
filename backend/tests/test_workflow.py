import hashlib,io,zipfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

def test_auth_signup_login_and_protection():
    with TestClient(app) as anon:
        assert anon.get("/api/v1/cases").status_code==401
        data={"full_name":"Alex Investigator","email":"alex@example.com","password":"SafeLocalPass123"}
        assert anon.post("/api/v1/auth/signup",json={**data,"email":"not-an-email"}).status_code==422
        assert anon.post("/api/v1/auth/signup",json={**data,"password":"short"}).status_code==422
        signup=anon.post("/api/v1/auth/signup",json=data)
        assert signup.status_code==201 and signup.json()["role"]=="INVESTIGATOR"
        assert "httponly" in signup.headers["set-cookie"].lower()
        assert anon.get("/api/v1/auth/me").json()["email"]==data["email"]
        duplicate=anon.post("/api/v1/auth/signup",json=data)
        assert duplicate.status_code==409
        with __import__('app.db.database',fromlist=['db_session']).db_session() as db:
            stored=db.execute("SELECT password_hash FROM users WHERE email=?",(data["email"],)).fetchone()[0]
        assert stored!="SafeLocalPass123" and stored.startswith("$argon2")
        assert anon.post("/api/v1/auth/logout").status_code==200
        assert anon.get("/api/v1/auth/me").status_code==401
        assert anon.post("/api/v1/auth/login",json={"email":data["email"],"password":"wrongpassword"}).status_code==401
        assert anon.post("/api/v1/auth/login",json={"email":data["email"],"password":data["password"]}).status_code==200

def test_supplementary_files_are_classified_and_preserved(client):
    cid=client.post("/api/v1/cases",json={"name":"Supplementary"}).json()["case_id"]
    samples=[("report.pdf",b"%PDF-1.7\nsynthetic report","application/pdf","DOCUMENT"),("notes.json",b'{"demo":true}',"application/json","DOCUMENT"),("photo.png",b"\x89PNG\r\n\x1a\nsynthetic image bytes","image/png","IMAGE")]
    for filename,data,mime,category in samples:
        response=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":(filename,data,mime)})
        assert response.status_code==201,response.text
        saved=response.json()
        assert saved["category"]==category and saved["processing_status"]=="STORED_AS_SUPPLEMENTARY_EVIDENCE"
        assert saved["working_copy_path"]=="" and Path(saved["file_path"]).read_bytes()==data
        assert not list((Path(saved["file_path"]).parent.parent/"working").glob("*"))
        assert client.get(f"/api/v1/evidence/{saved['evidence_id']}/acquisition").status_code==200
    pdf=client.get(f"/api/v1/cases/{cid}/evidence").json()[0]
    assert pdf["uploaded_by"] and pdf["case_id"]==cid
    assert client.post(f"/api/v1/cases/{cid}/parse",params={"evidence_id":pdf["evidence_id"]}).status_code==415
    investigation=client.post(f"/api/v1/cases/{cid}/investigate",json={"question":"What supplementary material is available?"}).json()
    assert any("supplementary file(s) are available" in r for r in investigation["recommendations"])
    withdrawn=client.delete(f"/api/v1/evidence/{pdf['evidence_id']}")
    assert withdrawn.status_code==200 and Path(pdf["file_path"]).exists()
    assert len(client.get(f"/api/v1/cases/{cid}/evidence").json())==2

def test_open_original_is_read_only_and_category_aware(client):
    cid=client.post("/api/v1/cases",json={"name":"Open original"}).json()["case_id"]
    pdf_bytes=b"%PDF-1.4\nsynthetic inline sample"
    pdf=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("sample.pdf",pdf_bytes,"application/pdf")}).json()
    opened=client.get(f"/api/v1/evidence/{pdf['evidence_id']}/open")
    assert opened.status_code==200 and opened.content==pdf_bytes
    assert opened.headers["content-disposition"].startswith("inline;")
    assert opened.headers["x-content-type-options"]=="nosniff"
    hive_bytes=b"regf"+b"header-only fixture; not a valid hive"
    hive=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("sample.dat",hive_bytes,"application/octet-stream")}).json()
    downloaded=client.get(f"/api/v1/evidence/{hive['evidence_id']}/open")
    assert downloaded.status_code==200 and downloaded.content==hive_bytes
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    docx_stream=io.BytesIO()
    with zipfile.ZipFile(docx_stream,"w") as archive:
        archive.writestr("[Content_Types].xml","<Types/>")
        archive.writestr("word/document.xml","<document>synthetic</document>")
    docx_bytes=docx_stream.getvalue()
    docx=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("synthetic-resume.docx",docx_bytes,"application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert docx.status_code==201 and docx.json()["category"]=="DOCUMENT" and not docx.json()["working_copy_path"]
    docx_open=client.get(f"/api/v1/evidence/{docx.json()['evidence_id']}/open")
    assert docx_open.status_code==200 and docx_open.content==docx_bytes
    assert docx_open.headers["content-disposition"].startswith("attachment;")
    assert client.delete(f"/api/v1/evidence/{pdf['evidence_id']}").status_code==200
    assert client.get(f"/api/v1/evidence/{pdf['evidence_id']}/open").status_code==404

def test_case_ownership_and_soft_delete(client):
    owned=client.post("/api/v1/cases",json={"name":"Private case"}).json()
    assert owned["case_number"].startswith("CASE-") and owned["status"]=="OPEN"
    other=client.post("/api/v1/auth/signup",json={"full_name":"Second Investigator","email":"second@example.com","password":"AnotherSafePass123"})
    assert other.status_code==201
    assert client.get(f"/api/v1/cases/{owned['case_id']}").status_code==404
    client.post("/api/v1/auth/login",json={"email":"workflow@example.com","password":"SecureTestPass123"})
    assert client.delete(f"/api/v1/cases/{owned['case_id']}").status_code==200

def test_registry_extension_requires_hive_signature(client):
    cid=client.post("/api/v1/cases",json={"name":"Header validation"}).json()["case_id"]
    r=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("realistic.hive",b"regf"+b"\x00"*20,"application/octet-stream")})
    assert r.status_code==201 and r.json()["category"]=="REGISTRY_HIVE"
    assert r.json()["validation_status"]=="HEADER_PRESENT_UNVERIFIED"

def test_health_and_openapi(client):
    assert client.get("/api/v1/health").json()["status"]=="ok"
    assert client.get("/openapi.json").status_code==200

def test_full_workflow(client):
    case=client.post("/api/v1/cases",json={"name":"Scenario A","description":"controlled test"}); assert case.status_code==201
    cid=case.json()["case_id"]; assert client.get(f"/api/v1/cases/{cid}").status_code==200
    payload=b"regf"+b"controlled upload fixture that is not a verified hive"
    up=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("sample.dat",payload,"application/octet-stream")})
    assert up.status_code==201,up.text
    item=up.json(); assert item["sha256"]==hashlib.sha256(payload).hexdigest(); assert item["file_size"]==len(payload)
    original=Path(item["file_path"]); working=Path(item["working_copy_path"])
    assert original.read_bytes()==payload and working.read_bytes()==payload and original!=working
    assert client.get(f"/api/v1/cases/{cid}/acquisition-log").json()
    detail=client.get(f"/api/v1/evidence/{item['evidence_id']}").json()
    assert {m["key"] for m in detail["metadata"]}>={"original_filename","file_size","sha256","acquired_at"}
    parsed=client.post(f"/api/v1/cases/{cid}/parse",params={"evidence_id":item["evidence_id"]}).json()
    assert parsed["is_demo"] is True and "DEMO" in parsed["records"][0]["validation_status"]
    assert len(client.get(f"/api/v1/cases/{cid}/records").json())==1
    assert original.read_bytes()==payload
    graph=client.get(f"/api/v1/cases/{cid}/graph").json()
    assert graph["is_demo"] and len(graph["nodes"])==2 and len(graph["edges"])==1
    assert graph["edges"][0]["relationship_type"]=="DEMO_PARSE_OUTPUT"
    assert "not a forensic relationship" in graph["edges"][0]["explanation"]
    inv=client.post(f"/api/v1/cases/{cid}/investigate",json={"question":"What is in this sample?"}).json()
    assert inv["is_demo"] and inv["claims"][0]["verification_status"]=="NOT_ESTABLISHED"
    assert client.get(f"/api/v1/cases/{cid}/verifications").json()
    assert client.get(f"/api/v1/evidence/{item['evidence_id']}").status_code==200

def test_duplicate_upload_is_deterministic(client):
    cid=client.post("/api/v1/cases",json={"name":"Dup"}).json()["case_id"]
    a=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("x.hive",b"regf-same bytes","application/octet-stream")}).json()
    b=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("x.hive",b"regf-same bytes","application/octet-stream")}).json()
    assert not a["duplicate"] and b["duplicate"] and a["evidence_id"]==b["evidence_id"]
    assert len(client.get(f"/api/v1/cases/{cid}/evidence").json())==1
    assert client.get(f"/api/v1/cases/{cid}/acquisition-log").json()[0]["action"]=="DUPLICATE_UPLOAD"

def test_validation_and_missing_case(client):
    assert client.post("/api/v1/cases",json={"name":""}).status_code==422
    assert client.get("/api/v1/cases/nope").status_code==404
    assert client.post("/api/v1/cases/nope/evidence/upload",files={"file":("x.dat",b"regf")}).status_code==404
    cid=client.post("/api/v1/cases",json={"name":"x"}).json()["case_id"]
    assert client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("x.exe",b"no")}).status_code==415
    assert client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("x.dat",b"not a hive")}).status_code==415
    assert client.post(f"/api/v1/cases/{cid}/investigate",json={"question":"x"}).status_code==422

def test_demo_seed_and_integrations(client):
    cid=client.post("/api/v1/cases",json={"name":"Demo"}).json()["case_id"]
    seeded=client.post(f"/api/v1/cases/{cid}/demo/seed")
    assert seeded.status_code==201 and seeded.json()["demo"] and len(seeded.json()["evidence"])==3
    files=client.get(f"/api/v1/cases/{cid}/evidence").json()
    assert len(files)==3 and all(f["is_demo"] for f in files)
    assert all(f["working_copy_path"] for f in files if f["category"].startswith("REGISTRY"))
    assert all(not f["working_copy_path"] for f in files if f["category"]=="DOCUMENT")
    export=next(f for f in files if f["original_filename"].endswith(".reg"))
    opened=client.get(f"/api/v1/evidence/{export['evidence_id']}/open")
    assert opened.status_code==200 and opened.headers["content-disposition"].startswith("inline;")
    parsed=client.post(f"/api/v1/cases/{cid}/parse",params={"evidence_id":export["evidence_id"]})
    assert parsed.status_code==200 and parsed.json()["records"][0]["validation_status"]=="DEMO_ONLY"
    assert client.get(f"/api/v1/cases/{cid}/records").json()[0]["validation_status"]=="DEMO_ONLY"
    graph=client.get(f"/api/v1/cases/{cid}/graph").json()
    assert len(graph["nodes"])==2 and len(graph["edges"])==1 and graph["is_demo"]

def test_demo_graph_never_invents_real_evidence_links():
    from app.integrations.adapters import DemoGraph
    graph=DemoGraph().get_graph(case_id="case-1",records=[{"evidence_id":"record-1","file_id":"file-1","source_file":"actual.hive","artifact_type":"RunMRU","validation_status":"VALIDATED"}])
    assert graph["nodes"]==[] and graph["edges"]==[] and graph["is_demo"]

def test_case_update(client):
    c=client.post("/api/v1/cases",json={"name":"old"}).json()
    r=client.patch(f"/api/v1/cases/{c['case_id']}",json={"name":"new"})
    assert r.json()["name"]=="new"

def test_adapter_failures_are_sanitized(client,monkeypatch):
    import app.api.routes as routes
    cid=client.post("/api/v1/cases",json={"name":"Adapter errors"}).json()["case_id"]
    class Broken:
        name="broken"
        def get_graph(self,**kwargs): raise RuntimeError("internal diagnostics")
        def investigate(self,**kwargs): raise RuntimeError("internal diagnostics")
        def verify(self,**kwargs): raise RuntimeError("internal diagnostics")
        def parse(self,**kwargs): raise RuntimeError("internal diagnostics")
    monkeypatch.setattr(routes,"graph_adapter",Broken())
    monkeypatch.setattr(routes,"verifier",Broken())
    assert client.get(f"/api/v1/cases/{cid}/graph").json()=={"detail":"Graph service is unavailable."}
    assert client.post(f"/api/v1/cases/{cid}/investigate",json={"question":"Check the case evidence"}).json()=={"detail":"Investigation or verification adapter is unavailable."}
    claim={"claim_id":"c1","claim_text":"Claim","evidence_ids":[],"reasoning":"test"}
    assert client.post(f"/api/v1/cases/{cid}/verify",json={"claims":[claim]}).json()=={"detail":"Verification service is unavailable."}

def test_parser_unavailable_is_a_service_error(client,monkeypatch):
    import app.api.routes as routes
    cid=client.post("/api/v1/cases",json={"name":"Parser error"}).json()["case_id"]
    uploaded=client.post(f"/api/v1/cases/{cid}/evidence/upload",files={"file":("sample.dat",b"regf-test bytes","application/octet-stream")}).json()
    class Broken:
        name="broken"
        def parse(self,**kwargs): raise RuntimeError("private diagnostics")
    monkeypatch.setattr(routes,"parser",Broken())
    response=client.post(f"/api/v1/cases/{cid}/parse",params={"evidence_id":uploaded["evidence_id"]})
    assert response.status_code==503 and response.json()=={"detail":"Parser adapter is unavailable."}

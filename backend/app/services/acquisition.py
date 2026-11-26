import hashlib, ntpath, os, shutil, uuid
import codecs
from pathlib import Path
from datetime import datetime, timezone
import json
import xml.etree.ElementTree as ET
import zipfile
from fastapi import UploadFile, HTTPException
from app.core.config import settings
from app.db.database import db_session

CHUNK=1024*1024
REGISTRY_HIVE_EXTENSIONS={".dat",".hive",".bin"}
REGISTRY_EXPORT_EXTENSIONS={".reg"}
DOCUMENT_EXTENSIONS={".pdf",".txt",".csv",".json",".xml",".docx"}
IMAGE_EXTENSIONS={".jpg",".jpeg",".png",".webp"}
OTHER_FORENSIC_EXTENSIONS={".evtx",".log"}
ALLOWED_EXTENSIONS=REGISTRY_HIVE_EXTENSIONS|REGISTRY_EXPORT_EXTENSIONS|DOCUMENT_EXTENSIONS|IMAGE_EXTENSIONS|OTHER_FORENSIC_EXTENSIONS
ACCEPTED_EXTENSIONS_TEXT=", ".join(sorted(ALLOWED_EXTENSIONS))

def _check_declared_mime(mime,suffix):
    mime=(mime or "application/octet-stream").split(";",1)[0].strip().lower()
    if mime in {"application/octet-stream","binary/octet-stream","application/x-binary"}: return
    allowed={
        ".pdf":{"application/pdf"},".docx":{"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},".jpg":{"image/jpeg"},".jpeg":{"image/jpeg"},".png":{"image/png"},".webp":{"image/webp"},
        ".txt":{"text/plain"},".csv":{"text/csv","application/csv","application/vnd.ms-excel","text/plain"},
        ".json":{"application/json","text/json","text/plain"},".xml":{"application/xml","text/xml","text/plain"},
        ".reg":{"text/plain","application/x-regedit"},".log":{"text/plain"},".evtx":{"application/octet-stream","application/x-evtx"},
        ".dat":{"application/x-hive"},".hive":{"application/x-hive"},".bin":{"application/x-hive"},
    }
    if mime not in allowed.get(suffix,set()): raise HTTPException(415,"Uploaded content type does not match the selected file category.")

def _validate_content(path,suffix,mime):
    _check_declared_mime(mime,suffix)
    with path.open("rb") as source: head=source.read(32)
    if not head: raise HTTPException(422,"Empty evidence files are not accepted.")
    if suffix in REGISTRY_HIVE_EXTENSIONS:
        if not head.startswith(b"regf"): raise HTTPException(415,"Registry hive files must have the Windows hive header. This check does not establish that the hive is valid or parseable.")
        return "REGISTRY_HIVE","HEADER_PRESENT_UNVERIFIED"
    if suffix in REGISTRY_EXPORT_EXTENSIONS:
        with path.open("rb") as source: raw=source.read(2048)
        text=raw.decode("utf-8-sig",errors="replace").lstrip("\ufeff\x00\r\n ")
        if not (text.startswith("Windows Registry Editor Version") or text.startswith("REGEDIT4")):
            raise HTTPException(415,".reg files must begin with a recognized Windows Registry export header.")
        return "REGISTRY_EXPORT","EXPORT_HEADER_RECOGNIZED"
    if suffix==".pdf":
        if not head.startswith(b"%PDF-"): raise HTTPException(415,"The file does not have a PDF signature.")
        return "DOCUMENT","CONTENT_SIGNATURE_VALIDATED"
    if suffix==".docx":
        try:
            with zipfile.ZipFile(path) as archive: names=set(archive.namelist())
        except (zipfile.BadZipFile,OSError):
            raise HTTPException(415,"The .docx file is not a readable Office Open XML document.")
        if not {"[Content_Types].xml","word/document.xml"}.issubset(names):
            raise HTTPException(415,"The .docx file is missing required Word document parts.")
        return "DOCUMENT","CONTENT_VALIDATED"
    if suffix in IMAGE_EXTENSIONS:
        valid=(suffix in {".jpg",".jpeg"} and head.startswith(b"\xff\xd8\xff")) or (suffix==".png" and head.startswith(b"\x89PNG\r\n\x1a\n")) or (suffix==".webp" and head[:4]==b"RIFF" and head[8:12]==b"WEBP")
        if not valid: raise HTTPException(415,"Image file signature does not match its extension.")
        return "IMAGE","CONTENT_SIGNATURE_VALIDATED"
    if suffix==".json":
        try: json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError,json.JSONDecodeError): raise HTTPException(415,"The .json file is not valid UTF-8 JSON.")
        return "DOCUMENT","CONTENT_VALIDATED"
    if suffix==".xml":
        try: ET.parse(path)
        except (ET.ParseError,UnicodeDecodeError): raise HTTPException(415,"The .xml file is not well-formed UTF-8 XML.")
        return "DOCUMENT","CONTENT_VALIDATED"
    if suffix in {".txt",".csv",".log"}:
        try:
            decoder=codecs.getincrementaldecoder("utf-8-sig")()
            with path.open("rb") as source:
                for block in iter(lambda:source.read(CHUNK),b""):
                    if b"\x00" in block: raise UnicodeDecodeError("utf-8",block,0,1,"binary content")
                    decoder.decode(block)
            decoder.decode(b"",final=True)
        except UnicodeDecodeError: raise HTTPException(415,"Text evidence must contain valid UTF-8 text, not binary content.")
        return ("OTHER_FORENSIC_EVIDENCE","TEXT_CONTENT_VALIDATED") if suffix==".log" else ("DOCUMENT","TEXT_CONTENT_VALIDATED")
    if suffix==".evtx":
        if not head.startswith(b"ElfFile\x00"): raise HTTPException(415,"The .evtx file is missing the expected event-log header.")
        return "OTHER_FORENSIC_EVIDENCE","HEADER_PRESENT_UNVERIFIED"
    raise HTTPException(415,f"Unsupported evidence extension. Accepted: {ACCEPTED_EXTENSIONS_TEXT}.")

async def acquire_upload(case_id: str, upload: UploadFile, uploaded_by: str, is_demo: bool = False):
    filename=Path(ntpath.basename(upload.filename or "")).name
    if not filename or filename in {".",".."}: raise HTTPException(422,"A valid filename is required.")
    suffix=Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS: raise HTTPException(415,f"Unsupported evidence extension. Accepted: {ACCEPTED_EXTENSIONS_TEXT}.")
    folder=Path(settings.storage_path)/case_id
    originals=folder/"originals"; working=folder/"working"
    originals.mkdir(parents=True,exist_ok=True); working.mkdir(parents=True,exist_ok=True)
    temp=originals/(".upload-"+uuid.uuid4().hex)
    digest=hashlib.sha256(); size=0
    original=None; work=None; created_original=False; created_work=False
    try:
        with temp.open("xb") as target:
            while chunk:=await upload.read(CHUNK):
                size+=len(chunk)
                if size>settings.max_upload_bytes: raise HTTPException(413,"Evidence exceeds configured upload size limit.")
                digest.update(chunk); target.write(chunk)
        category,validation_status=_validate_content(temp,suffix,upload.content_type)
        sha=digest.hexdigest(); now=datetime.now(timezone.utc).isoformat(); file_id=str(uuid.uuid4())
        stored=f"{sha}{suffix}"; original=originals/stored; work=working/(file_id+suffix)
        with db_session() as db:
            duplicate=db.execute("SELECT * FROM evidence_files WHERE case_id=? AND sha256=?",(case_id,sha)).fetchone()
            if duplicate:
                temp.unlink(missing_ok=True)
                db.execute("INSERT INTO acquisition_logs VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),case_id,duplicate["evidence_id"],"DUPLICATE_UPLOAD",f"Same SHA-256 already acquired; existing original reused: {sha}",now))
                return dict(duplicate), True
            if original.exists():
                if original.stat().st_size!=size: raise RuntimeError("SHA-256 storage collision detected")
                temp.unlink(missing_ok=True)
            else:
                os.replace(temp,original)
                created_original=True
            working_path=""
            if category in {"REGISTRY_HIVE","REGISTRY_EXPORT"}:
                shutil.copyfile(original,work)
                created_work=True
                working_path=str(work.resolve())
            row={"evidence_id":file_id,"case_id":case_id,"original_filename":filename,"stored_filename":stored,"file_path":str(original.resolve()),"working_copy_path":working_path,"file_size":size,"sha256":sha,"acquired_at":now,"media_type":upload.content_type,"is_demo":int(is_demo),"category":category,"validation_status":validation_status,"uploaded_by":uploaded_by,"is_withdrawn":0}
            columns=",".join(row.keys()); placeholders=",".join("?" for _ in row)
            db.execute(f"INSERT INTO evidence_files({columns}) VALUES({placeholders})",tuple(row.values()))
            activity="ACQUIRED"; processing="working copy created for Registry adapter" if working_path else "supplementary evidence stored without Registry parsing"
            if is_demo: activity="DEMO_SAMPLE_ACQUIRED"
            db.execute("INSERT INTO acquisition_logs VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),case_id,file_id,activity,f"Original preserved; {processing}; category={category}; validation={validation_status}; sha256={sha}"+("; synthetic repository fixture, not real forensic evidence." if is_demo else ""),now))
            metadata=[("original_filename",filename),("file_size",str(size)),("sha256",sha),("acquired_at",now),("category",category),("validation_status",validation_status),("uploaded_by",uploaded_by),("media_type",upload.content_type or "")]
            if is_demo: metadata.append(("demo_notice","Synthetic repository fixture; not real forensic evidence."))
            for k,v in metadata: db.execute("INSERT INTO evidence_metadata VALUES(?,?,?,?)",(str(uuid.uuid4()),file_id,k,str(v)))
        return row,False
    except Exception:
        temp.unlink(missing_ok=True)
        if created_work and work: work.unlink(missing_ok=True)
        if created_original and original: original.unlink(missing_ok=True)
        raise
    finally: await upload.close()

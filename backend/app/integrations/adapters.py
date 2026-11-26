from typing import Protocol, Any
from uuid import uuid4
from app.schemas.contracts import Claim, ClaimStatus

class RegistryParserAdapter(Protocol):
    name: str
    def parse(self, *, case_id: str, file_id: str, source_file: str, working_copy_path: str) -> list[dict[str, Any]]: ...
class EvidenceGraphAdapter(Protocol):
    name: str
    def get_graph(self, *, case_id: str, records: list[dict]) -> dict[str, Any]: ...
class RAGInvestigationAdapter(Protocol):
    name: str
    def investigate(self, *, question: str, records: list[dict], graph: dict, supplementary_files: list[dict]) -> dict[str, Any]: ...
class VerificationAdapter(Protocol):
    name: str
    def verify(self, *, claim: Claim, records: list[dict]) -> Claim: ...

class DemoParser:
    name="demo-parser"
    def parse(self, *, case_id, file_id, source_file, working_copy_path):
        return [{"artifact_type":"DEMO_SAMPLE","source_file":source_file,"source_path":"DEMO://controlled-fixture","extracted_data":{"notice":"Synthetic demonstration record. No Registry hive was parsed.","fixture":"evidencearch-demo-v1"},"event_timestamp":None,"timestamp_type":None,"user_identifier":None,"device_identifier":None,"file_hash":None,"parser_version":"demo-parser/1.0","validation_status":"DEMO_ONLY","source_evidence_id":file_id}]
class DemoGraph:
    name="demo-graph"
    def get_graph(self, *, case_id, records):
        """Show only explicit file-to-record provenance for synthetic fixture rows."""
        demo_records=[r for r in records if r.get("validation_status")=="DEMO_ONLY" and r.get("file_id") and r.get("evidence_id")]
        nodes=[]; edges=[]; seen_files=set()
        for record in demo_records:
            file_id=record["file_id"]
            file_node_id=f"file-{file_id}"
            record_node_id=f"record-{record['evidence_id']}"
            if file_id not in seen_files:
                nodes.append({"id":file_node_id,"label":record["source_file"],"kind":"demo_evidence_file","evidence_id":file_id,"is_demo":True,"explanation":"Synthetic fixture file; not real collected evidence."})
                seen_files.add(file_id)
            nodes.append({"id":record_node_id,"label":record["artifact_type"],"kind":"demo_evidence_record","evidence_id":record["evidence_id"],"source_evidence_id":file_id,"validation_status":"DEMO_ONLY","is_demo":True,"explanation":"Synthetic demo record; the Registry bytes were not parsed."})
            edges.append({"id":f"demo-link-{file_id}-{record['evidence_id']}","source":file_node_id,"target":record_node_id,"relationship_type":"DEMO_PARSE_OUTPUT","evidence_ids":[file_id,record["evidence_id"]],"is_demo":True,"explanation":"Demo-only provenance link created to illustrate how a parser record references its source file. It is not a forensic relationship or finding."})
        message=("Synthetic sample provenance links only. No real Registry contents or forensic relationships are represented." if nodes else "No synthetic demo records to display yet. Add the controlled demo fixtures and parse a Registry sample.")
        return {"case_id":case_id,"nodes":nodes,"edges":edges,"adapter":self.name,"is_demo":True,"message":message}
class DemoInvestigator:
    name="demo-investigator"
    def investigate(self, *, question, records, graph, supplementary_files=None):
        ids=[r["evidence_id"] for r in records if r.get("validation_status")=="DEMO_ONLY"]
        claims=[]
        if ids: claims=[{"claim_id":str(uuid4()),"claim_text":"A synthetic demo fixture is available for interface testing; it is not a Registry finding.","evidence_ids":ids[:1],"reasoning":"Deterministic demo response; no forensic conclusion is produced."}]
        gaps=[]
        if not any(r.get("validation_status") not in {"DEMO_ONLY","UNVERIFIED_LEGACY"} for r in records):
            gaps.append({"category":"NOT_COLLECTED","explanation":"No validated Registry parser records are available in this demo workflow.","why_it_matters":"Without validated parsed records, this prototype cannot assess Registry activity.","recommended_next_step":"Acquire a supported Registry hive and integrate Member 2's validated parser."})
        supplements=[f for f in (supplementary_files or []) if f.get("category") in {"DOCUMENT","IMAGE","OTHER_FORENSIC_EVIDENCE"}]
        recommendations=["Integrate Member 2's validated Registry parser and Member 4's grounded investigation adapter."]
        if supplements: recommendations.append(f"{len(supplements)} supplementary file(s) are available; content extraction is not implemented in the demo adapter.")
        return {"claims":claims,"uncertainty":["Demo adapter only. No LLM, RAG retrieval, or forensic interpretation was performed."],"recommendations":recommendations,"evidence_gaps":gaps}
class UnconfiguredVerifier:
    name="unconfigured-verifier"
    def verify(self, *, claim, records):
        claim.verification_status=ClaimStatus.NOT_ESTABLISHED
        claim.verification_explanation="No independent verification engine is configured; claim status is NOT_ESTABLISHED."
        return claim

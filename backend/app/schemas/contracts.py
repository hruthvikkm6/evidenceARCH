from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls,value):
        if not value.strip(): raise ValueError("Full name cannot be blank.")
        return value.strip()
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
class UserOut(BaseModel):
    user_id: str; full_name: str; email: EmailStr; role: str; is_active: bool
    created_at: datetime

class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    status: str = "OPEN"
    @field_validator("name")
    @classmethod
    def name_not_blank(cls,value):
        if not value.strip(): raise ValueError("Case name cannot be blank.")
        return value.strip()
    @field_validator("status")
    @classmethod
    def valid_status(cls,value):
        if value not in {"OPEN","IN_PROGRESS","CLOSED","ARCHIVED"}: raise ValueError("Invalid case status.")
        return value
class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    @field_validator("name")
    @classmethod
    def updated_name_not_blank(cls,value):
        if value is not None and not value.strip(): raise ValueError("Case name cannot be blank.")
        return value.strip() if value is not None else value
    @field_validator("status")
    @classmethod
    def valid_updated_status(cls,value):
        if value is not None and value not in {"OPEN","IN_PROGRESS","CLOSED","ARCHIVED"}: raise ValueError("Invalid case status.")
        return value
class CaseOut(BaseModel):
    case_id: str; case_number: str | None = None; name: str; description: str; investigator_id: str | None = None; status: str = "OPEN"; evidence_count: int = 0; investigation_count: int = 0; created_at: datetime; updated_at: datetime
class FileCategory(str, Enum):
    REGISTRY_HIVE="REGISTRY_HIVE"; REGISTRY_EXPORT="REGISTRY_EXPORT"; DOCUMENT="DOCUMENT"; IMAGE="IMAGE"; OTHER_FORENSIC_EVIDENCE="OTHER_FORENSIC_EVIDENCE"; DEMO="DEMO"; LEGACY_UNCLASSIFIED="LEGACY_UNCLASSIFIED"
class EvidenceRecordIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    evidence_id: str | None=None
    case_id: str
    artifact_type: str
    source_file: str
    source_path: str
    extracted_data: dict[str, Any]
    event_timestamp: datetime | None=None
    timestamp_type: str | None=None
    user_identifier: str | None=None
    device_identifier: str | None=None
    file_hash: str | None=None
    parser_version: str
    validation_status: str
    source_evidence_id: str
class EvidenceRecordOut(EvidenceRecordIn):
    evidence_id: str
class ClaimStatus(str, Enum):
    SUPPORTED="SUPPORTED"; CONTRADICTED="CONTRADICTED"; NOT_ESTABLISHED="NOT_ESTABLISHED"
class Claim(BaseModel):
    claim_id: str
    claim_text: str
    evidence_ids: list[str]
    reasoning: str
    verification_status: ClaimStatus | None=None
    verification_explanation: str | None=None
class InvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
class EvidenceGapCategory(str, Enum):
    NOT_COLLECTED="NOT_COLLECTED"
    UNAVAILABLE="UNAVAILABLE"
    EXPECTED_BUT_NOT_FOUND="EXPECTED_BUT_NOT_FOUND"
    MAY_NEVER_HAVE_EXISTED="MAY_NEVER_HAVE_EXISTED"
class EvidenceGap(BaseModel):
    category: EvidenceGapCategory
    explanation: str = Field(min_length=1, max_length=2000)
    why_it_matters: str = Field(min_length=1, max_length=2000)
    recommended_next_step: str = Field(min_length=1, max_length=2000)
class InvestigationResult(BaseModel):
    investigation_id: str
    question: str
    claims: list[Claim]
    uncertainty: list[str]
    recommendations: list[str]
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    adapter: str
    is_demo: bool
class VerifyRequest(BaseModel):
    claims: list[Claim] = Field(min_length=1, max_length=30)

from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentType(str, Enum):
    strategy = "strategy"
    research = "research"
    plan = "plan"
    operational = "operational"
    meeting_notes = "meeting_notes"
    other = "other"


class DocumentStatus(str, Enum):
    actual = "actual"
    draft = "draft"
    archived = "archived"
    superseded = "superseded"
    unknown = "unknown"


class ChatMode(str, Enum):
    search = "search"
    contradictions = "contradictions"
    promises = "promises"
    gaps = "gaps"
    write = "write"
    validate = "validate"
    research = "research"


class PromiseStatus(str, Enum):
    open = "open"
    fulfilled = "fulfilled"
    overdue = "overdue"
    no_data = "no_data"


class ContradictionStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


# --- Request models ---

class ChatRequest(BaseModel):
    message: str
    mode: Optional[ChatMode] = None
    file: Optional[str] = None  # base64
    session_id: Optional[UUID] = None


class DocumentPatch(BaseModel):
    status: Optional[DocumentStatus] = None
    is_anchor: Optional[bool] = None
    is_style_anchor: Optional[bool] = None
    superseded_by: Optional[UUID] = None


class ContradictionPatch(BaseModel):
    status: ContradictionStatus
    resolved_by: Optional[UUID] = None


class PromisePatch(BaseModel):
    status: PromiseStatus
    resolved_at: Optional[date] = None
    notes: Optional[str] = None


# --- Response models ---

class SourceRef(BaseModel):
    document_id: UUID
    title: str
    status: DocumentStatus
    hierarchy_level: int
    date: Optional[date] = None
    section: Optional[str] = None
    confluence_url: Optional[str] = None


class FactItem(BaseModel):
    statement: str
    source: SourceRef


class ChatResponse(BaseModel):
    answer: str
    facts: list[FactItem]
    hypotheses: list[str]
    warnings: list[str]
    requires_verification: list[str]
    metadata: dict


class DocumentOut(BaseModel):
    id: UUID
    title: str
    type: Optional[DocumentType] = None
    status: DocumentStatus
    hierarchy_level: Optional[int] = None
    segment: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[date] = None
    is_anchor: bool
    is_style_anchor: bool
    confluence_url: Optional[str] = None
    chunk_count: Optional[int] = None
    indexed_at: Optional[datetime] = None

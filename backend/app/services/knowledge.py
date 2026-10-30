"""Knowledge Hub: document ingestion, PostgreSQL full-text retrieval, and proof-carrying answers."""
import json
import re
from pathlib import PurePath

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..ai import prompts
from ..ai.client import AIClient
from ..ai.schemas import KnowledgeAnswer
from ..config import get_settings
from ..db import is_postgres
from ..errors import AppError, bad_request, conflict
from ..logging_setup import get_logger
from ..models import AnswerRun, Decision, Document, KnowledgeChunk, Meeting, Task
from .common import get_member, get_project, iso, keywords, member_names, sha256
from .tasks import serialize_task

log = get_logger("knowledge")

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
CHUNK_WORDS, CHUNK_OVERLAP = 160, 40


# ---------------------------------------------------------------------------- ingestion

def extract_text(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    """Return [(page_number, text)]. Raises 422 for unsupported, unreadable or empty files."""
    ext = PurePath(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise bad_request("unsupported_file_type", f"Unsupported file type '{ext or 'none'}'. Use PDF, TXT or Markdown.")
    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise bad_request("invalid_pdf", "The file does not look like a PDF.")
        import fitz  # PyMuPDF

        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise bad_request("encrypted_pdf", "Password-protected PDFs are not supported.")
                pages = [(i + 1, page.get_text("text")) for i, page in enumerate(doc)]
        except AppError:
            raise
        except Exception as exc:
            raise bad_request("unreadable_pdf", "The PDF could not be read.") from exc
    else:
        for enc in ("utf-8-sig", "cp1252"):
            try:
                pages = [(None, data.decode(enc))]
                break
            except UnicodeDecodeError:
                continue
        else:
            raise bad_request("unreadable_text", "The text file encoding could not be read.")
    pages = [(n, t.replace("\x00", "").strip()) for n, t in pages]
    pages = [(n, t) for n, t in pages if t]
    if not pages or sum(len(t) for _, t in pages) < 20:
        raise bad_request("no_extractable_text",
                          "No extractable text was found. Scanned/image-only PDFs are not supported (no OCR).")
    return pages


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[tuple[int | None, str]]:
    chunks = []
    for page_no, body in pages:
        words = body.split()
        start = 0
        while start < len(words):
            piece = " ".join(words[start:start + CHUNK_WORDS])
            chunks.append((page_no, piece))
            if start + CHUNK_WORDS >= len(words):
                break
            start += CHUNK_WORDS - CHUNK_OVERLAP
    return chunks


def ingest_document(db: Session, *, project_id: int, filename: str, data: bytes, title: str | None,
                    uploaded_by: int | None) -> Document:
    project = get_project(db, project_id)
    if uploaded_by is not None:
        get_member(db, project, uploaded_by, field="uploaded_by")
    if len(data) > get_settings().max_upload_bytes:
        raise bad_request("file_too_large", f"Files must be at most {get_settings().max_upload_bytes // (1024 * 1024)} MB.")
    if not data:
        raise bad_request("empty_file", "The uploaded file is empty.")
    safe_name = PurePath(filename or "upload").name[:300]
    pages = extract_text(safe_name, data)
    full_text = "\n\n".join(t for _, t in pages)
    content_hash = sha256(full_text)
    dup = db.scalar(select(Document).where(Document.project_id == project.id, Document.content_hash == content_hash))
    if dup:
        raise conflict("duplicate_document", f"Identical content already exists as '{dup.title}' v{dup.version_number}.",
                       {"document_id": dup.id})
    doc_title = (title or PurePath(safe_name).stem).strip()[:300] or safe_name
    latest = db.scalar(select(func.max(Document.version_number)).where(Document.project_id == project.id,
                                                                       Document.title == doc_title)) or 0
    for prev in db.scalars(select(Document).where(Document.project_id == project.id, Document.title == doc_title,
                                                  Document.document_status == "current")):
        prev.document_status = "superseded"
    doc = Document(project_id=project.id, title=doc_title, source_filename=safe_name, content_text=full_text,
                   content_hash=content_hash, version_number=latest + 1, document_status="current",
                   uploaded_by=uploaded_by)
    db.add(doc)
    db.flush()
    for i, (page_no, piece) in enumerate(chunk_pages(pages)):
        db.add(KnowledgeChunk(document_id=doc.id, chunk_index=i, content=piece, page_number=page_no,
                              content_hash=sha256(piece)))
    db.commit()
    log.info("document_ingested", extra={"document_id": doc.id, "project_id": project.id,
                                         "version": doc.version_number, "chars": len(full_text)})
    return doc


def serialize_document(d: Document, names: dict[int, str], chunk_count: int | None = None) -> dict:
    return {"id": d.id, "project_id": d.project_id, "title": d.title, "source_filename": d.source_filename,
            "version_number": d.version_number, "document_status": d.document_status,
            "review_state": "unreviewed upload",  # uploads are never treated as approved decisions
            "uploaded_by_name": names.get(d.uploaded_by) if d.uploaded_by else None,
            "created_at": iso(d.created_at), "chunk_count": chunk_count, "chars": len(d.content_text)}


def list_documents(db: Session, project_id: int) -> list[dict]:
    project = get_project(db, project_id)
    names = member_names(db, project.workspace_id)
    counts = dict(db.execute(select(KnowledgeChunk.document_id, func.count()).join(Document)
                             .where(Document.project_id == project_id).group_by(KnowledgeChunk.document_id)).all())
    docs = db.scalars(select(Document).where(Document.project_id == project_id)
                      .order_by(Document.title, Document.version_number.desc()))
    return [serialize_document(d, names, counts.get(d.id, 0)) for d in docs]


# ---------------------------------------------------------------------------- retrieval

_PG_QUERIES = {
    "chunk": """SELECT kc.id, ts_rank(to_tsvector('english', kc.content), q) AS rank
        FROM knowledge_chunks kc JOIN documents d ON d.id = kc.document_id, to_tsquery('english', :tsq) q
        WHERE d.project_id = :pid AND to_tsvector('english', kc.content) @@ q ORDER BY rank DESC LIMIT :lim""",
    "meeting": """SELECT m.id, ts_rank(to_tsvector('english', m.title || ' ' || coalesce(m.summary, '') || ' ' ||
        m.raw_notes), q) AS rank FROM meetings m, to_tsquery('english', :tsq) q WHERE m.project_id = :pid AND
        to_tsvector('english', m.title || ' ' || coalesce(m.summary, '') || ' ' || m.raw_notes) @@ q
        ORDER BY rank DESC LIMIT :lim""",
    "decision": """SELECT d.id, ts_rank(to_tsvector('english', d.statement || ' ' || coalesce(d.evidence, '')), q)
        AS rank FROM decisions d, to_tsquery('english', :tsq) q WHERE d.project_id = :pid AND
        to_tsvector('english', d.statement || ' ' || coalesce(d.evidence, '')) @@ q ORDER BY rank DESC LIMIT :lim""",
    "task": """SELECT t.id, ts_rank(to_tsvector('english', t.title || ' ' || coalesce(t.description, '') || ' ' ||
        coalesce(t.outcome, '')), q) AS rank FROM tasks t, to_tsquery('english', :tsq) q WHERE t.project_id = :pid
        AND to_tsvector('english', t.title || ' ' || coalesce(t.description, '') || ' ' || coalesce(t.outcome, ''))
        @@ q ORDER BY rank DESC LIMIT :lim""",
}


def _py_rank(rows: list[tuple[int, str]], terms: list[str], limit: int) -> list[int]:
    """Portable fallback (used with SQLite in tests): prefix-match term counting."""
    scored = []
    for rid, body in rows:
        toks = re.findall(r"[a-z0-9]+", body.lower())
        score = sum(1 for term in terms if any(tok.startswith(term[:6]) for tok in toks))
        if score:
            scored.append((score, rid))
    return [rid for _, rid in sorted(scored, key=lambda x: (-x[0], x[1]))[:limit]]


def _rank(db: Session, kind: str, project_id: int, terms: list[str], limit: int) -> list[int]:
    if not terms:
        return []
    if is_postgres(db):
        tsq = " | ".join(f"{t}:*" for t in terms)  # terms are [a-z0-9]+ only, so safe for to_tsquery
        return [r[0] for r in db.execute(text(_PG_QUERIES[kind]), {"tsq": tsq, "pid": project_id, "lim": limit})]
    if kind == "chunk":
        rows = db.execute(select(KnowledgeChunk.id, KnowledgeChunk.content).join(Document)
                          .where(Document.project_id == project_id)).all()
    elif kind == "meeting":
        rows = [(m.id, f"{m.title} {m.summary or ''} {m.raw_notes}")
                for m in db.scalars(select(Meeting).where(Meeting.project_id == project_id))]
    elif kind == "decision":
        rows = [(d.id, f"{d.statement} {d.evidence or ''}")
                for d in db.scalars(select(Decision).where(Decision.project_id == project_id))]
    else:
        rows = [(t.id, f"{t.title} {t.description or ''} {t.outcome or ''}")
                for t in db.scalars(select(Task).where(Task.project_id == project_id))]
    return _py_rank(rows, terms, limit)


def _excerpt(body: str, terms: list[str], width: int = 420) -> str:
    low = body.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=0)
    start = max(0, pos - width // 3)
    snippet = body[start:start + width].strip()
    return ("…" if start else "") + snippet + ("…" if start + width < len(body) else "")


def search(db: Session, project_id: int, q: str, limit: int = 6) -> dict:
    project = get_project(db, project_id)
    names = member_names(db, project.workspace_id)
    terms = keywords(q)
    chunk_ids = _rank(db, "chunk", project_id, terms, limit)
    meeting_ids = _rank(db, "meeting", project_id, terms, limit)
    decision_ids = _rank(db, "decision", project_id, terms, limit)
    task_ids = _rank(db, "task", project_id, terms, limit)

    def ordered(model, ids):
        rows = {r.id: r for r in db.scalars(select(model).where(model.id.in_(ids or [-1])))}
        return [rows[i] for i in ids if i in rows]

    from .decisions import serialize_decision

    return {
        "query": q,
        "terms": terms,
        "chunks": [{"id": c.id, "document_id": c.document_id, "document_title": c.document.title,
                    "version_number": c.document.version_number, "document_status": c.document.document_status,
                    "chunk_index": c.chunk_index, "page_number": c.page_number,
                    "excerpt": _excerpt(c.content, terms)} for c in ordered(KnowledgeChunk, chunk_ids)],
        "meetings": [{"id": m.id, "title": m.title, "meeting_at": iso(m.meeting_at),
                      "extraction_status": m.extraction_status,
                      "excerpt": _excerpt(f"{m.summary or ''}\n{m.raw_notes}", terms)}
                     for m in ordered(Meeting, meeting_ids)],
        "decisions": [serialize_decision(d, names) for d in ordered(Decision, decision_ids)],
        "tasks": [serialize_task(t, names) for t in ordered(Task, task_ids)],
    }


# ---------------------------------------------------------------------------- proof-carrying answers

ABSTAIN = "I could not find records in this project that answer this question. I will not infer an answer."
_DECISION_WORDS = {"decision", "decided", "decide", "approved", "approve", "agreed", "policy", "choose", "chosen"}
_TASK_WORDS = {"task", "tasks", "owner", "owns", "assigned", "who", "deadline", "due", "blocked", "blocker", "status"}
_APPROVAL_RE = re.compile(r"\b(approved|approve|decided|agreed|signed off|confirmed|finali[sz]ed)\b", re.I)
_NEGATION_RE = re.compile(r"\b(not|no|never|without|pending|yet to|undecided|proposed|discussed|considered?)\b", re.I)
_APPROVED_DECISION_STATUSES = {"active", "superseded"}  # superseded decisions were approved at the time


def _stems(text: str) -> set[str]:
    return {t[:5] for t in keywords(text, 80)} - {"team"}


def _approval_unsupported(claim: str, sources: list[dict]) -> bool:
    """True when a claim asserts an approval that none of its cited records establish.

    A source existing is not proof: a meeting that only *discussed* a change does not support "X was approved".
    Approval is established by an approved decision record, or by one source sentence that itself records the
    approval; either must cover more than half of the claim's topic terms.
    """
    if not _APPROVAL_RE.search(claim) or _NEGATION_RE.search(claim):
        return False
    topic = _stems(_APPROVAL_RE.sub(" ", claim))
    if not topic:
        return False

    def covers(text: str) -> bool:
        return len(topic & _stems(text)) / len(topic) > 0.5

    for src in sources:
        if src.get("type") == "decision":
            record = " ".join(str(src.get(k) or "") for k in ("label", "text", "evidence", "approved_by", "approved_at"))
            if src.get("status") in _APPROVED_DECISION_STATUSES and covers("decision " + record):
                return False
            continue
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+", src.get("text") or ""):
            if _APPROVAL_RE.search(sentence) and not _NEGATION_RE.search(sentence) and covers(sentence):
                return False
    return True


def _evidence(db: Session, project_id: int, question: str) -> tuple[list[dict], list[str]]:
    """Assemble evidence strictly from the selected project. Returns (records, intents)."""
    found = search(db, project_id, question, limit=6)
    q_tokens = set(re.findall(r"[a-z]+", question.lower()))
    intents = [name for name, words in (("decision", _DECISION_WORDS), ("task", _TASK_WORDS)) if q_tokens & words]
    records: dict[str, dict] = {}

    for d in found["decisions"]:
        records[f"decision:{d['id']}"] = {"type": "decision", "record_id": d["id"], "label": d["code"],
                                          "status": d["status"], "text": d["statement"], "evidence": d["evidence"],
                                          "approved_by": d["approved_by_name"], "approved_at": d["approved_at"],
                                          "meeting_id": d["meeting_id"], "meeting_title": d["meeting_title"]}
    for t in found["tasks"]:
        records[f"task:{t['id']}"] = {"type": "task", "record_id": t["id"], "label": f"TASK-{t['id']}",
                                      "status": t["status"], "text": t["title"], "owner": t["owner_name"],
                                      "due_at": t["due_at"], "outcome": t["outcome"]}
    for m in found["meetings"][:4]:
        records[f"meeting:{m['id']}"] = {"type": "meeting", "record_id": m["id"], "label": m["title"],
                                         "status": m["extraction_status"], "date": m["meeting_at"],
                                         "text": m["excerpt"]}
    for c in found["chunks"]:
        records[f"chunk:{c['id']}"] = {"type": "document_chunk", "record_id": c["id"], "document_id": c["document_id"],
                                       "label": f"{c['document_title']} v{c['version_number']}"
                                                + (f" p.{c['page_number']}" if c["page_number"] else ""),
                                       "status": c["document_status"], "text": c["excerpt"]}
    # Structured SQL facts are added only when the question is about decisions and something matched,
    # so unrelated questions still abstain instead of receiving a dump of the ledger.
    if "decision" in intents and records:
        from .decisions import list_decisions

        for d in list_decisions(db, project_id, "active")[:10]:
            records.setdefault(f"decision:{d['id']}", {
                "type": "decision", "record_id": d["id"], "label": d["code"], "status": d["status"],
                "text": d["statement"], "evidence": d["evidence"], "approved_by": d["approved_by_name"],
                "approved_at": d["approved_at"], "meeting_id": d["meeting_id"], "meeting_title": d["meeting_title"]})
    return [{"id": k, **v} for k, v in records.items()], intents


def ask(db: Session, project_id: int, question: str, ai: AIClient, actor_id: int | None = None) -> dict:
    project = get_project(db, project_id)
    if actor_id is not None:
        get_member(db, project, actor_id, field="actor_id")
    evidence, intents = _evidence(db, project_id, question)
    by_id = {e["id"]: e for e in evidence}

    def finish(status: str, payload: dict, model: str | None) -> dict:
        cited = sorted({sid for c in payload.get("claims", []) for sid in c["source_ids"]}
                       | {sid for c in payload.get("conflicts", []) for sid in c["source_ids"]})
        run = AnswerRun(project_id=project_id, asked_by=actor_id, question=question, status=status,
                        answer_json=payload, source_ids=cited, model=model)
        db.add(run)
        db.commit()
        log.info("knowledge_answer", extra={"project_id": project_id, "status": status, "sources": len(cited),
                                            "evidence_records": len(evidence), "answer_run_id": run.id})
        return {"answer_run_id": run.id, "status": status, "question": question, **payload,
                "sources": [by_id[s] for s in cited if s in by_id], "retrieved_count": len(evidence),
                "intents": intents}

    if not evidence:
        return finish("insufficient_evidence", {"answer": ABSTAIN, "claims": [], "conflicts": [],
                                                "missing_information": "No matching records were retrieved.",
                                                "rejected_claims": []}, None)

    prompt = "\n\n".join([
        f"Project: {project.name}",
        f"Question: {question}",
        prompts.data_block("evidence_records", json.dumps(evidence, indent=1, default=str)),
    ])
    result = ai.generate_json(task="knowledge_answer", system=prompts.ANSWER_SYSTEM, prompt=prompt,
                              schema=KnowledgeAnswer)

    valid_claims, rejected = [], []
    for c in result.claims:
        bad = [s for s in c.source_ids if s not in by_id]
        if bad:
            rejected.append({"text": c.text, "source_ids": c.source_ids, "invalid_source_ids": bad,
                             "reason": "invalid_source_ids"})
        elif _approval_unsupported(c.text, [by_id[s] for s in c.source_ids]):
            rejected.append({"text": c.text, "source_ids": c.source_ids, "reason": "approval_not_established"})
        else:
            valid_claims.append({"text": c.text, "source_ids": c.source_ids})
    conflicts = [{"description": c.description, "source_ids": [s for s in c.source_ids if s in by_id]}
                 for c in result.conflicts]
    status = result.status
    if status == "supported" and not valid_claims:
        status = "insufficient_evidence"
    if status == "conflicting" and not any(c["source_ids"] for c in conflicts) and not valid_claims:
        status = "insufficient_evidence"
    if status == "insufficient_evidence":
        answer = result.answer if not result.claims else ABSTAIN
        valid_claims = []
    else:
        # The free-text answer is shown only when every claim survived validation.
        answer = result.answer if not rejected else "Some claims were not supported by the cited records and were " \
                                                     "removed. Only verified claims are shown below."
    if rejected:
        log.warning("knowledge_answer_invalid_sources", extra={"project_id": project_id, "rejected": len(rejected)})
    return finish(status, {"answer": answer, "claims": valid_claims, "conflicts": conflicts,
                           "missing_information": result.missing_information, "rejected_claims": rejected},
                  getattr(ai, "model", None))

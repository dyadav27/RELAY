import hashlib
import re
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import AppError, bad_request, not_found
from ..models import Member, Project

STOPWORDS = set(
    """a an and are as at be by for from has have how i in is it its of on or that the this to was were what when
    where which who whom why will with did do does we our you your about any there their them they been being
    can could should would may might into than then also just only over under not no yes so if""".split()
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC so comparisons are consistent."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return aware(dt).astimezone(UTC).isoformat()
    return dt.isoformat()


def date_to_due(d: date | None) -> datetime | None:
    # A due date means "by end of that day" (UTC) for overdue calculation.
    return datetime.combine(d, time(23, 59, 59), tzinfo=UTC) if d else None


def now() -> datetime:
    return datetime.now(UTC)


def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise AppError(404, "not_found", f"Project {project_id} does not exist.")
    return project


def get_member(db: Session, project: Project, member_id: int | None, *, field: str = "member", required: bool = True,
               must_be_active: bool = False) -> Member | None:
    if member_id is None:
        if required:
            raise bad_request("missing_member", f"{field} is required.")
        return None
    member = db.get(Member, member_id)
    if not member or member.workspace_id != project.workspace_id:
        raise bad_request("invalid_member", f"{field} {member_id} is not a member of this workspace.")
    if must_be_active and not member.is_active:
        raise bad_request("inactive_member", f"{field} {member.name} is not active.")
    return member


def member_names(db: Session, workspace_id: int) -> dict[int, str]:
    return {m.id: m.name for m in db.scalars(select(Member).where(Member.workspace_id == workspace_id))}


def keywords(text: str, limit: int = 12) -> list[str]:
    seen: list[str] = []
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        if len(tok) > 1 and tok not in STOPWORDS and tok not in seen:
            seen.append(tok)
    return seen[:limit]


def token_overlap(a: str, b: str) -> float:
    ta, tb = set(keywords(a, 50)), set(keywords(b, 50))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_source(quote: str | None, source: str) -> bool:
    """True when the (whitespace/case-normalised) quote appears in the source text."""
    if not quote:
        return False
    q = normalize_ws(quote).strip(" .\"'“”")
    return bool(q) and q in normalize_ws(source)


def ensure_found(obj, entity: str, entity_id):
    if obj is None:
        raise not_found(entity, entity_id)
    return obj

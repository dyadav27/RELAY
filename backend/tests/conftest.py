"""Test harness: fresh database per test (SQLite in-memory by default, or TEST_DATABASE_URL for PostgreSQL)
and a scripted fake AI client that still goes through the real JSON/Pydantic validation path."""
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("LOG_FILE_PATH", os.path.join(os.path.dirname(__file__), "..", "logs", "test.jsonl"))
os.environ["GEMINI_API_KEY"] = ""
# Tests must never reach the real database: the app's own engine (used by the startup seed hook) points at
# throwaway SQLite, and the demo seed hook is disabled. Real env vars take precedence over the root .env.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_DEMO_DATA"] = "false"

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB and any(h in TEST_DB for h in ("supabase.com", "supabase.co")):
    raise RuntimeError("TEST_DATABASE_URL points at Supabase; the test fixtures DROP ALL TABLES. Use a disposable DB.")

from app import models as m  # noqa: E402
from app.ai.client import get_ai_client, parse_model_output  # noqa: E402
from app.db import Base, get_db, make_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


class FakeAI:
    model = "fake-model"

    def __init__(self):
        self.queue: dict[str, list] = {}
        self.calls: list[tuple[str, str]] = []

    def add(self, task: str, value) -> None:
        self.queue.setdefault(task, []).append(value)

    def generate_json(self, *, task, system, prompt, schema):
        self.calls.append((task, prompt))
        items = self.queue.get(task)
        if not items:
            from app.ai.client import AINotConfigured

            raise AINotConfigured("no scripted response")
        value = items.pop(0)
        if isinstance(value, Exception):
            raise value
        return parse_model_output(json.dumps(value), schema)


@pytest.fixture
def engine():
    if TEST_DB:
        from app.config import Settings

        eng = make_engine(Settings(database_url=TEST_DB).sqlalchemy_url)
        Base.metadata.drop_all(eng)
    else:
        from sqlalchemy import create_engine, event

        eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(eng, "connect")
        def _fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def Session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(Session):
    s = Session()
    yield s
    s.close()


@pytest.fixture
def ai():
    return FakeAI()


@pytest.fixture
def client(Session, ai):
    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_ai_client] = lambda: ai
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def demo(db):
    """Seeded demo scenario; returns lookups by name/title."""
    seed(db)
    db.expire_all()
    members = {x.name: x for x in db.scalars(select(m.Member))}
    projects = {x.name: x for x in db.scalars(select(m.Project))}
    meetings = {x.title: x for x in db.scalars(select(m.Meeting))}
    tasks = {x.title: x for x in db.scalars(select(m.Task))}
    decisions = list(db.scalars(select(m.Decision).order_by(m.Decision.id)))
    return {"members": members, "projects": projects, "meetings": meetings, "tasks": tasks, "decisions": decisions,
            "pay": projects["Payment Gateway Integration"], "onb": projects["Customer Onboarding Portal"],
            "mgr": members["Demo Manager"], "rahul": members["Rahul"], "priya": members["Priya"],
            "amit": members["Amit"]}

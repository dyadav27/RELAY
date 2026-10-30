# RELAY

**AI-Powered Knowledge Integrity & Work Continuity Platform**
*Never lose the context behind a decision or the work that follows it.*

## Problem

Teams lose context when people miss meetings, go on leave, change roles or hand over work. Decisions live in meeting notes, work lives in task trackers, and the link between *why* something was decided and *what work depends on it* is lost. Task managers track assignments and meeting summarisers capture talk, but neither notices when this week's discussion quietly contradicts last month's approved decision.

## Solution

RELAY keeps one connected record of meetings, decisions and work:

1. **Meeting Intelligence**: raw notes become a structured *draft* (summary, confirmed vs proposed decisions, action items, owners, deadlines, blockers, open questions). Every item quotes its evidence. Nothing is official until a person approves it.
2. **Work Continuity**: tasks keep one identity across meetings (carry-forward, never duplicate), with a full event history of ownership, status, deadlines, blockers and outcomes.
3. **Decision Integrity Engine** *(primary differentiator)*: new discussions are compared with approved decisions of the same project. Drift is flagged with evidence from both sides and the work it may affect. Only a human can supersede a decision, and lineage is preserved.
4. **Knowledge Hub with Proof-Carrying Answers** *(second differentiator)*: answers are broken into claims that must cite retrieved RELAY records. The server validates every citation and withholds unsupported answers.
5. **Handover Copilot & Catch-up briefs**: SQL decides which work is in scope; AI only narrates; transfers are approved by a manager in a single transaction.

### Why the Decision Integrity Engine matters

Most costly rework comes from teams acting on a decision that was quietly changed, or changing a decision without realising what depended on it. RELAY makes that drift visible when it happens: *"DEC-0001 says use the internal auth service; Tuesday's review proposed Auth0; these 3 tasks depend on it."* It never silently rewrites history. Approving a change creates a new decision, marks the old one `superseded` (not deleted), records who approved it and why, keeps both source meetings, and flags affected tasks for review.

## Architecture

```
Browser (React SPA) ──same-origin /api──▶ FastAPI (one service)
                                            ├── services/  business rules + transactions
                                            ├── ai/        Gemini client, prompts, Pydantic output schemas
                                            ├── SQLAlchemy ─▶ PostgreSQL (Supabase) + full-text GIN indexes
                                            └── JSON logs ─▶ stdout + LOG_FILE_PATH
```

* One FastAPI app serves both the API and the built frontend (`frontend/dist`), so the browser never talks to Gemini and never sees the key.
* AI output is **data, never actions**: the model returns JSON that is validated with Pydantic, cross-checked against the database (IDs, quotes, participants), and only persisted after human approval.

### Technology stack

| Layer | Choice |
|---|---|
| Frontend | React 18, Vite, TypeScript (strict), Tailwind CSS, React Router, Lucide icons |
| Backend | Python, FastAPI, SQLAlchemy 2, Pydantic 2 |
| Database | PostgreSQL (Supabase), Alembic migrations, PostgreSQL full-text search |
| AI | Gemini via `google-genai`, model set by `GEMINI_MODEL`, JSON output + server validation |
| Documents | PyMuPDF (text PDFs), TXT, Markdown |
| Deploy | Docker on Render + Supabase Postgres |

## Data flow

**Meeting → draft → approval**
1. `POST /api/meetings` stores the notes verbatim with a SHA-256 `source_hash`.
2. `POST /api/meetings/{id}/extract` sends the notes to Gemini, validates the `MeetingExtraction` schema, then post-processes on the server:
   * suggested owners must appear in the notes **and** match exactly one participant, otherwise `owner_id = null` with a reason (`ambiguous`, `not_a_participant`, `not_in_notes`);
   * deadline phrases must appear verbatim in the notes, and an ISO date is kept only if its phrase is verified (dates are never invented);
   * evidence quotes are checked against the notes and unverified ones are flagged;
   * existing tasks with similar titles are suggested for carry-forward/link.
   It then runs Decision Integrity analysis.
3. The reviewer edits the summary and decisions, chooses *create / carry forward / link / exclude* per action item, and approves. `POST /approve` re-checks that the notes hash is unchanged, atomically flips `extracted → approved` (a duplicate approval matches 0 rows and gets 409), and creates decisions/tasks/links/events in one transaction.

**Decision drift**: active decisions of the *same project* are ranked and sent with the new statements. The model classifies pairs as `consistent | proposal | potential_conflict | conditional_change | revisit | explicit_replacement`. The server drops references to decisions or tasks it did not send, replaces "old evidence" with the stored decision evidence, and keeps the new quote only if it is found in the notes. Review actions: **Confirm new decision** (supersede), **Record as proposal**, **Dismiss**.

**Proof-carrying answers**: question → keywords → PostgreSQL FTS over chunks, meetings, decisions and tasks (project-filtered) → evidence records with IDs like `decision:3`, `chunk:11` → Gemini returns `{status, answer, claims[{text, source_ids}], conflicts}` → the server removes any claim citing an ID that was not retrieved, downgrades `supported` with no surviving claims to `insufficient_evidence`, and persists the run (`answer_runs`). If nothing is retrieved, RELAY abstains without calling the model. Statuses: `supported`, `conflicting`, `insufficient_evidence`. No confidence percentages. A valid reference shows what was cited; it does not prove the model read it correctly, and the UI says so.

## Database schema

`workspaces, members, projects, meetings, meeting_participants, tasks, meeting_tasks, task_events, decisions, decision_relations, decision_alerts, documents, knowledge_chunks, handovers, handover_tasks` plus `answer_runs` (audit of knowledge answers).

Integrity is enforced in the database as well as in code:
* `UNIQUE(meeting_id, task_id)` on `meeting_tasks` (no duplicate associations);
* `CHECK (status <> 'completed' OR outcome is non-empty)` on `tasks`;
* `CHECK (status <> 'active' OR approved_by AND approved_at)` on `decisions`;
* check constraints on every status/classification enum; `from_member_id <> to_member_id` on handovers;
* `tasks.version` as SQLAlchemy `version_id_col` (stale writes give **409**);
* expression GIN indexes for full-text search (`alembic/versions/0001_initial_schema.py`).

## API

Interactive OpenAPI docs: **`/docs`** (ReDoc at `/redoc`). Errors always use `{"error": {"code", "message", "details", "request_id"}}`.

| Area | Endpoints |
|---|---|
| System | `GET /api/health`, `GET /api/dashboard?project_id`, `GET /api/projects`, `GET /api/members`, `GET /api/search` |
| Meetings | `POST/GET /api/meetings`, `GET/PATCH /api/meetings/{id}`, `POST /api/meetings/{id}/extract`, `POST /api/meetings/{id}/approve` |
| Tasks | `GET/POST /api/tasks`, `GET/PATCH /api/tasks/{id}`, `POST …/carry-forward`, `POST …/close`, `POST …/reopen`, `GET …/history` |
| Decisions | `GET /api/decisions`, `GET /api/decision-alerts`, `POST /api/decisions/analyze`, `POST /api/decision-alerts/{id}/resolve` |
| Knowledge | `POST/GET /api/knowledge/documents`, `GET /api/knowledge/documents/{id}`, `GET /api/knowledge/search`, `POST /api/knowledge/ask` |
| Handover | `POST /api/handovers/generate`, `GET /api/handovers`, `GET /api/handovers/{id}`, `POST /api/handovers/{id}/approve`, `POST /api/catch-up` |

## AI configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Server-side key. If missing, AI endpoints return **503 `ai_not_configured`**. RELAY never fabricates AI output. |
| `GEMINI_MODEL` | Default `gemini-2.5-flash` (verified live: 2–5 s per call, all smoke tests passed). `gemini-3.8-flash` returned correct JSON but took 43–100 s per call and hit `504 DEADLINE_EXCEEDED`, so it is not recommended for interactive use. |
| `GEMINI_TIMEOUT_SECONDS` | Default 45; values below 10 are raised to 10 (Gemini's minimum deadline). Client timeouts and provider `504 DEADLINE_EXCEEDED` both give **504 `ai_timeout`** with the notes preserved and extraction retryable. |

Provider errors: `429` (quota/rate limit) → **503 `ai_rate_limited`** (the message says whether it is the daily quota); a transient `503 UNAVAILABLE` is retried once; anything else → **502 `ai_provider_error`**.

> **Free-tier quota.** A free Gemini API key allows only **20 requests per day per model** for `gemini-2.5-flash`. A meeting extraction uses 2 calls (extraction + decision drift), a knowledge answer 1, a handover/catch-up brief 1. Enable billing on the Google Cloud project before a public demo.

Without a key, the handover and catch-up briefs still work in a clearly labelled **records-only** mode, built deterministically from the database.

## Logging

Every request gets an `X-Request-ID` (incoming header honoured, otherwise generated) that is attached to every log line and error body. Logs are JSON lines to stdout **and** `LOG_FILE_PATH`. Events include `request_completed`, `meeting_created`, `meeting_extracted`, `meeting_extraction_failed`, `meeting_approved`, `task_created`, `task_reassigned`, `task_carried_forward`, `task_closed`, `task_reopened`, `decision_analysis`, `decision_superseded`, `decision_alert_resolved`, `document_ingested`, `knowledge_answer`, `handover_generated`, `handover_approved`, `*_rolled_back`, `db_error`. AI calls log `request_id, event, model, latency_ms, outcome, error_type`. Notes, document text, keys and passwords are never logged (only sizes/IDs).

> Render's filesystem is ephemeral: `/tmp/relay.jsonl` is lost on restart or redeploy unless you attach a persistent disk and point `LOG_FILE_PATH` at it. stdout logs remain in Render's log viewer.

## Local setup

Prerequisites: Python 3.12+, Node 20+, a PostgreSQL database (Supabase or local). If you set no `DATABASE_URL`, the app falls back to a local SQLite file for quick trials; full-text ranking then uses a simpler portable keyword match.

```bash
# backend
python -m venv .venv
.venv/Scripts/activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r backend/requirements-dev.txt
cp .env.example .env              # fill in DATABASE_URL and GEMINI_API_KEY

cd backend
alembic upgrade head
python -m app.seed                # synthetic demo data (only seeds an empty database)
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm ci
npm run dev                       # http://localhost:5173, proxies /api to :8000
# or: npm run build  then open http://localhost:8000 (served by FastAPI)
```

`python -m app.seed --reset` wipes **all** rows and reseeds (local development only).

## Testing

```bash
cd backend
pytest -q                                                    # SQLite in-memory
TEST_DATABASE_URL=postgresql://user@host:5432/relay_test pytest -q   # real PostgreSQL (drops/creates tables!)
```

Tests never touch the database in `.env`: `conftest.py` forces `DATABASE_URL=sqlite://` and `SEED_DEMO_DATA=false` for the app process, and refuses a `TEST_DATABASE_URL` that points at Supabase (the fixtures drop all tables). Use a disposable local database for PostgreSQL runs.

Tests use a scripted fake AI that still goes through the real JSON + Pydantic validation path. Covered: meeting creation, invalid participants, invalid model output, missing/ambiguous owners, invented deadlines, proposal vs confirmed, duplicate associations (app + DB constraint), carry-forward identity, completed tasks not reopened, reassignment history, closure needs outcome (app + DB constraint), explicit reopen, duplicate approval, notes changed after extraction, drift detection with cross-project references dropped, supersession lineage, mark-as-proposal, abstention without AI call, invalid source IDs, cross-project isolation, AI timeout/provider failure, missing AI config, stale version 409, duplicate handover approval, handover rollback, document validation/versioning/dedup, health/dashboard/catch-up.

## Deployment (Render + Supabase)

1. **Supabase**: create a project and copy the **Session pooler** connection string (Project → Connect). Render needs the pooler because Supabase direct connections are IPv6-only. RELAY adds `sslmode=require` automatically for any non-local PostgreSQL host unless the URL sets `sslmode` itself.
2. **Render**: push this repo to GitHub, then *New → Blueprint* and select the repo (uses `render.yaml`, Docker runtime, region `frankfurt` to sit next to a Supabase `eu-central-1` database; change it if your Supabase region differs).
3. Set `DATABASE_URL` and `GEMINI_API_KEY` in the Render dashboard (`sync: false` secrets). `GEMINI_MODEL`, `LOG_FILE_PATH` and `SEED_DEMO_DATA` have defaults in `render.yaml`.
4. On start the container runs `alembic upgrade head` (a no-op when already at head), seeds the demo workspace **only if the `workspaces` table is empty** (existing data is never touched), and serves on `$PORT`. The health check is `/api/health`.
5. Open the service URL and confirm `/api/health` reports `"database": "postgresql"` and `"ai_configured": true`. `ai_configured` only means a key is set; confirm the model really works by running one meeting extraction.

### Deployment checklist

- [ ] `.env` is not committed (`git check-ignore .env` prints a match) and no key appears in `frontend/dist`.
- [ ] Render env: `DATABASE_URL` (Supabase **session pooler**, port 5432) and `GEMINI_API_KEY` set as secrets; `GEMINI_MODEL=gemini-2.5-flash`.
- [ ] Gemini project has billing enabled (or you accept 20 requests/day/model on the free tier).
- [ ] Render region matches the Supabase region.
- [ ] After deploy: `/api/health` 200, `/docs` 200, `/overview` and a nested route such as `/meetings/1` load after a browser refresh.
- [ ] One live meeting extraction succeeds; check the `ai_call` log line in Render's log viewer (latency, `outcome: success`).
- [ ] Free plan: the service sleeps when idle; open it a minute before a demo. File logs in `/tmp` are lost on restart (stdout logs persist in Render).

## Environment variables

| Name | Required | Default |
|---|---|---|
| `DATABASE_URL` | yes (prod) | local SQLite file |
| `GEMINI_API_KEY` | for AI features | none |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` |
| `GEMINI_TIMEOUT_SECONDS` | no | `45` (minimum effective value 10) |
| `LOG_FILE_PATH` | no | `backend/logs/relay.jsonl` |
| `LOG_LEVEL` | no | `INFO` |
| `SEED_DEMO_DATA` | no | `false` |
| `FRONTEND_DIST` | no | `frontend/dist` |

## Demo scenario (synthetic)

Workspace **Northwind Labs (Demo)**; every person, company and figure is fictional and is labelled as demo data in the UI. Project **Payment Gateway Integration** with Rahul, Priya, Amit and Demo Manager:
* *Kickoff* approved **DEC-0001 "use the existing internal authentication service"** and created four tasks;
* *Weekly review* discussed migrating to Auth0. This is **a proposal, not an approved change**, and it produces pending alert ALERT-0001 against DEC-0001 with three affected tasks;
* tasks cover open (overdue), in progress, blocked, completed with outcome, and carried forward;
* *Payment Security Sync* is logged but not extracted, so you can try the live AI workflow on it;
* one design document, plus a draft handover Rahul → Amit.

A second project, **Customer Onboarding Portal**, holds an Auth0 decision and a USD 12,000 budget. It exists to demonstrate that questions in the payment project never see it (*"What is the approved migration budget?"* abstains).

## Assumptions

* The demo-identity selector in the header records *who acted*; it is **not authentication**. Real deployments need auth and per-project authorisation in front of this API.
* One workspace; members belong to the workspace and can work on any of its projects.
* A due date means end of that day (UTC) for overdue calculation; "overdue" is computed, never stored.
* Uploaded documents are evidence, never approvals, and are labelled "unreviewed". A newer upload with the same title becomes a new version, and the older one is marked `superseded`.

## Known limitations

* The Gemini integration could not be exercised against the live API in this environment (no key was available). All AI paths are tested with a scripted client through the real validation code. Verify with your key and model.
* No OCR: scanned PDFs are rejected with a clear message.
* Retrieval is keyword full-text search (OR-of-prefix terms with `ts_rank`), not semantic search. Synonyms can be missed.
* Document-to-meeting links are heuristic (shared vocabulary), not stored relations.
* Blockers and unresolved questions live in the meeting's extraction draft, not in a dedicated table.
* No real-time collaboration, notifications delivery, or external integrations (Slack/Jira/Zoom), by design.
* The Docker image build was not run locally (Docker unavailable). The start command sequence was verified against a fresh PostgreSQL database.

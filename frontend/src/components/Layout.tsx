import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { Bell, Menu, Plus, Search, Wand2, UserCircle2 } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { CatchUpModal } from "./CatchUpModal";
import { MeetingFormModal } from "./MeetingFormModal";
import { Button, ErrorState, LoadingState, Spinner, StatusBadge } from "./ui";
import { useApp } from "../lib/context";
import { api, useApi } from "../lib/api";
import type { Alert } from "../lib/types";
import { relTime } from "../lib/format";

const UiActions = createContext<{ openCatchUp: () => void; openLogMeeting: () => void }>({
  openCatchUp: () => {}, openLogMeeting: () => {},
});
export const useUiActions = () => useContext(UiActions);

function GlobalSearch() {
  const { project } = useApp();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!project || q.trim().length < 2) { setRes(null); return; }
    const t = setTimeout(async () => {
      setBusy(true);
      try { setRes(await api(`/search?project_id=${project.id}&q=${encodeURIComponent(q.trim())}`)); }
      catch { setRes(null); }
      finally { setBusy(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [q, project]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); ref.current?.querySelector("input")?.focus(); }
    };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); window.removeEventListener("keydown", onKey); };
  }, []);

  const go = (path: string) => { setOpen(false); setQ(""); navigate(path); };
  const total = res ? res.meetings.length + res.tasks.length + res.decisions.length + res.chunks.length : 0;

  return (
    <div className="flex-1 min-w-0 max-w-xl relative" ref={ref}>
      <div className="relative flex items-center">
        <Search className="absolute left-3 w-4 h-4 text-slate-400 pointer-events-none" />
        <input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          aria-label="Search project records"
          className="w-full h-9 pl-9 pr-14 bg-surface rounded-lg border border-surface-border text-slate-900 placeholder:text-slate-400 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
          placeholder="Search decisions, meetings, tasks or documents…" />
        <div className="absolute right-2.5 hidden sm:flex items-center pointer-events-none">
          {busy ? <Spinner /> : <kbd className="font-mono text-[10px] bg-slate-200/70 border border-slate-300 px-1.5 py-0.5 rounded text-slate-600 font-medium">Ctrl K</kbd>}
        </div>
      </div>
      {open && res && (
        <div className="absolute top-11 left-0 right-0 bg-white border border-surface-border rounded-lg shadow-xl max-h-[70vh] overflow-y-auto z-50 text-xs">
          {total === 0 ? <p className="p-4 text-slate-500">No records in {project?.name} match “{q}”.</p> : (
            <div className="py-1">
              {res.decisions.map((d: any) => (
                <button key={`d${d.id}`} onClick={() => go(`/knowledge?tab=decisions&decision=${d.id}`)} className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-start gap-2">
                  <span className="font-mono text-[10px] text-indigo-600 font-bold mt-0.5 w-16 shrink-0">{d.code}</span>
                  <span className="flex-1 text-slate-700">{d.statement}</span><StatusBadge status={d.status} />
                </button>))}
              {res.meetings.map((m: any) => (
                <button key={`m${m.id}`} onClick={() => go(`/meetings/${m.id}`)} className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-start gap-2">
                  <span className="font-mono text-[10px] text-slate-500 mt-0.5 w-16 shrink-0">MEETING</span>
                  <span className="flex-1 text-slate-700 font-medium">{m.title}</span>
                </button>))}
              {res.tasks.map((t: any) => (
                <button key={`t${t.id}`} onClick={() => go(`/tasks/${t.id}`)} className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-start gap-2">
                  <span className="font-mono text-[10px] text-slate-500 mt-0.5 w-16 shrink-0">TASK-{t.id}</span>
                  <span className="flex-1 text-slate-700">{t.title}</span><StatusBadge status={t.status} />
                </button>))}
              {res.chunks.map((c: any) => (
                <button key={`c${c.id}`} onClick={() => go(`/knowledge?tab=documents&document=${c.document_id}`)} className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-start gap-2">
                  <span className="font-mono text-[10px] text-slate-500 mt-0.5 w-16 shrink-0">DOC</span>
                  <span className="flex-1 text-slate-600"><b className="text-slate-800">{c.document_title}</b> — {c.excerpt.slice(0, 120)}</span>
                </button>))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Notifications() {
  const { project, revision } = useApp();
  const [open, setOpen] = useState(false);
  const { data, loading, error } = useApi<Alert[]>(project ? `/decision-alerts?project_id=${project.id}&r=${revision}` : null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const count = data?.length ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button aria-label={`Notifications (${count} pending decision reviews)`} onClick={() => setOpen((o) => !o)}
        className="relative p-2 text-slate-500 hover:text-slate-800 transition-colors rounded-lg hover:bg-slate-100">
        <Bell className="w-5 h-5" />
        {count > 0 && <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-amber-500 ring-2 ring-white" />}
      </button>
      {open && (
        <div className="absolute right-0 top-11 w-80 bg-white border border-surface-border rounded-lg shadow-xl z-50 text-xs">
          <p className="px-3 py-2 border-b border-surface-border font-semibold text-slate-800">Pending decision reviews</p>
          {loading ? <LoadingState /> : error ? <div className="p-3"><ErrorState error={error} /></div> : count === 0 ? (
            <p className="p-3 text-slate-500">Nothing needs review in this project.</p>
          ) : data!.map((a) => (
            <Link key={a.id} to={`/meetings/${a.meeting.id}?tab=integrity`} onClick={() => setOpen(false)}
              className="block px-3 py-2.5 hover:bg-slate-50 border-b border-surface-border last:border-0">
              <p className="font-semibold text-slate-800">{a.existing_decision.code} · {a.classification.replace(/_/g, " ")}</p>
              <p className="text-slate-500 line-clamp-2">{a.proposed_statement}</p>
              <p className="text-slate-400 mt-0.5">{a.meeting.title} · {relTime(a.created_at)}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function DemoProfile() {
  const { members, actorId, setActorId } = useApp();
  const me = members.find((m) => m.id === actorId);
  return (
    <label className="hidden sm:flex items-center gap-2 pl-1" title="Demo identity selector. This is NOT authentication; it only records who performs actions in the demo.">
      <UserCircle2 className="w-8 h-8 text-indigo-300" />
      <div className="hidden xl:flex flex-col text-left">
        <select aria-label="Acting as (demo identity)" value={actorId ?? ""} onChange={(e) => setActorId(Number(e.target.value))}
          className="text-xs font-semibold text-slate-900 bg-transparent focus:outline-none cursor-pointer -ml-1">
          {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <span className="text-[11px] text-slate-500 leading-none mt-0.5">{me?.role ?? ""} · demo identity</span>
      </div>
    </label>
  );
}

export function Layout() {
  const { ready, bootError, project } = useApp();
  const [nav, setNav] = useState(false);
  const [catchUp, setCatchUp] = useState(false);
  const [logMeeting, setLogMeeting] = useState(false);

  return (
    <UiActions.Provider value={{ openCatchUp: () => setCatchUp(true), openLogMeeting: () => setLogMeeting(true) }}>
      <Sidebar open={nav} onClose={() => setNav(false)} />
      <div className="lg:pl-64 overflow-x-hidden">
        <header className="fixed top-0 left-0 lg:left-64 right-0 z-30 bg-white/90 backdrop-blur-md border-b border-surface-border">
          <div className="h-16 px-4 lg:px-8 flex items-center justify-between gap-3 lg:gap-6">
            <button aria-label="Open navigation" className="lg:hidden p-2 -ml-2 text-slate-600" onClick={() => setNav(true)}>
              <Menu className="w-5 h-5" />
            </button>
            <GlobalSearch />
            <div className="flex items-center gap-2 lg:gap-3 shrink-0">
              <Button icon={<Wand2 className="w-4 h-4 text-indigo-600" />} onClick={() => setCatchUp(true)} className="hidden md:inline-flex">
                Generate Brief
              </Button>
              <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => setLogMeeting(true)}>
                <span className="hidden sm:inline">Log Meeting</span>
              </Button>
              <Notifications />
              <div className="h-5 w-px bg-surface-border mx-1 hidden sm:block" />
              <DemoProfile />
            </div>
          </div>
        </header>
        <main className="w-full pt-16 bg-surface min-h-screen">
          <div className="p-4 lg:p-8 max-w-[1600px] mx-auto w-full min-w-0 flex flex-col gap-6">
            {bootError ? <ErrorState error={bootError} onRetry={() => location.reload()} />
              : !ready ? <LoadingState text="Connecting to RELAY…" />
              : !project ? <ErrorState error={{ message: "No projects exist yet. Seed the demo data (python -m app.seed) or create a project in the database." }} />
              : <Outlet />}
          </div>
        </main>
      </div>
      {project && <CatchUpModal open={catchUp} onClose={() => setCatchUp(false)} />}
      {project && <MeetingFormModal open={logMeeting} onClose={() => setLogMeeting(false)} />}
    </UiActions.Provider>
  );
}

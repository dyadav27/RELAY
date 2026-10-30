import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Ban, CheckCircle2, CornerUpRight, RotateCcw, ShieldAlert, UserRoundCog, CalendarClock, PlayCircle } from "lucide-react";
import { EventTimelineItem } from "../components/EventText";
import { Badge, Button, Callout, Card, ErrorState, Field, LoadingState, Modal, PageHeader, StatusBadge, Timeline, inputCls, textareaCls } from "../components/ui";
import { useApp } from "../lib/context";
import { api, ApiError, useApi } from "../lib/api";
import { useToast } from "../lib/toast";
import { fmtDate, label } from "../lib/format";
import type { Meeting, TaskDetail as TD } from "../lib/types";

type Action = "status" | "owner" | "deadline" | "blocker" | "carry" | "close" | "reopen" | null;

export function TaskDetail() {
  const { id } = useParams();
  const { project, members, actorId, revision, bump } = useApp();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<TD>(`/tasks/${id}?r=${revision}`);
  const { data: meetings } = useApi<Meeting[]>(`/meetings?project_id=${project!.id}`);
  const [action, setAction] = useState<Action>(null);
  const [f, setF] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  if (loading && !data) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const t = data.task;
  const closed = t.status === "completed" || t.status === "cancelled";
  const linked = new Set(data.meetings.map((m) => m.id));

  const open = (a: Action, init: Record<string, string> = {}) => { setF(init); setAction(a); };

  async function submit() {
    setBusy(true);
    try {
      const base = { version: t.version, actor_id: actorId };
      if (action === "status") await api(`/tasks/${t.id}`, { method: "PATCH", body: { ...base, status: f.status, blocker_note: f.status === "blocked" ? f.note : undefined, note: f.status !== "blocked" ? f.note || undefined : undefined } });
      if (action === "owner") await api(`/tasks/${t.id}`, { method: "PATCH", body: { ...base, owner_id: f.owner ? Number(f.owner) : null, note: f.note || undefined } });
      if (action === "deadline") await api(`/tasks/${t.id}`, { method: "PATCH", body: { ...base, due_at: f.due || null, deadline_text: f.text || null, note: f.note || undefined } });
      if (action === "blocker") await api(`/tasks/${t.id}`, { method: "PATCH", body: { ...base, blocker_note: f.note } });
      if (action === "carry") await api(`/tasks/${t.id}/carry-forward`, { body: { meeting_id: Number(f.meeting), actor_id: actorId, note: f.note || null } });
      if (action === "close") await api(`/tasks/${t.id}/close`, { body: { ...base, outcome: f.outcome, resolution: f.resolution || "completed" } });
      if (action === "reopen") await api(`/tasks/${t.id}/reopen`, { body: { ...base, reason: f.reason } });
      toast.success("Saved and recorded in task history.");
      setAction(null); bump(); await reload();
    } catch (e) {
      toast.error(e);
      if ((e as ApiError).code === "version_conflict") { setAction(null); await reload(); }
    } finally { setBusy(false); }
  }

  const valid = {
    status: !!f.status && f.status !== t.status && (f.status !== "blocked" || (f.note ?? "").trim().length > 2),
    owner: (f.owner ?? "") !== String(t.owner_id ?? ""), deadline: true, blocker: (f.note ?? "").trim().length > 2,
    carry: !!f.meeting, close: (f.outcome ?? "").trim().length >= 3, reopen: (f.reason ?? "").trim().length >= 3,
  }[action ?? "deadline"];

  return (
    <>
      <Link to="/tasks" className="text-xs text-slate-500 hover:text-indigo-700 flex items-center gap-1 -mb-3"><ArrowLeft className="w-3.5 h-3.5" />Tasks</Link>
      <PageHeader title={t.title} badge={<><StatusBadge status={t.status} /><StatusBadge status={t.priority} text={`${t.priority} priority`} />{t.is_overdue && <Badge tone="rose" dot>Overdue</Badge>}</>}
        description={<>TASK-{t.id} · {data.project.name} · version {t.version}</>}
        actions={!closed ? <>
          <Button icon={<PlayCircle className="w-4 h-4" />} onClick={() => open("status", { status: t.status })}>Status</Button>
          <Button icon={<UserRoundCog className="w-4 h-4" />} onClick={() => open("owner", { owner: String(t.owner_id ?? "") })}>Owner</Button>
          <Button icon={<CalendarClock className="w-4 h-4" />} onClick={() => open("deadline", { due: t.due_at?.slice(0, 10) ?? "", text: t.deadline_text ?? "" })}>Deadline</Button>
          <Button icon={<ShieldAlert className="w-4 h-4" />} onClick={() => open("blocker")}>Record blocker</Button>
          <Button icon={<CornerUpRight className="w-4 h-4" />} onClick={() => open("carry")}>Carry forward</Button>
          <Button variant="primary" icon={<CheckCircle2 className="w-4 h-4" />} onClick={() => open("close", { resolution: "completed" })}>Close</Button>
        </> : <Button icon={<RotateCcw className="w-4 h-4" />} onClick={() => open("reopen")}>Reopen…</Button>} />

      {data.decision_alerts.some((a) => a.status === "pending") && (
        <Callout tone="amber" title="A decision this task depends on is under review">
          {data.decision_alerts.filter((a) => a.status === "pending").map((a) => <span key={a.id}>Proposed change to {a.existing_decision.code} ({a.existing_decision.statement}): “{a.proposed_statement}” (<Link className="underline" to={`/meetings/${a.meeting.id}?tab=integrity`}>review</Link>) </span>)}
        </Callout>)}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col gap-6">
          <Card title="Details">
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="sm:col-span-2"><dt className="text-slate-500 font-semibold uppercase tracking-wider text-[11px]">Description</dt><dd className="text-slate-700 mt-1 whitespace-pre-wrap">{t.description || "—"}</dd></div>
              <div className="sm:col-span-2"><dt className="text-slate-500 font-semibold uppercase tracking-wider text-[11px]">Acceptance criteria</dt><dd className="text-slate-700 mt-1 whitespace-pre-wrap">{t.acceptance_criteria || "—"}</dd></div>
              {t.outcome && <div className="sm:col-span-2"><dt className="text-slate-500 font-semibold uppercase tracking-wider text-[11px]">Outcome</dt><dd className="text-slate-800 mt-1 p-2.5 rounded-md bg-cyan-50/60 border border-cyan-200">{t.outcome}</dd></div>}
            </dl>
          </Card>
          <Card title="History" subtitle="Ownership, status and meeting changes">
            <Timeline>{[...data.events].reverse().map((e) => <EventTimelineItem key={e.id} e={e} />)}</Timeline>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <Card title="Ownership & timing">
            <dl className="flex flex-col gap-2.5 text-xs">
              <div className="flex justify-between gap-2"><dt className="text-slate-500">Owner</dt><dd className="font-semibold text-slate-800">{t.owner_name ?? <Badge tone="amber">Unassigned</Badge>}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-slate-500">Due</dt><dd className={t.is_overdue ? "text-rose-600 font-semibold" : "text-slate-800"}>{fmtDate(t.due_at)}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-slate-500">Deadline as stated</dt><dd className="text-slate-800 text-right">{t.deadline_text ?? "—"}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-slate-500">Created</dt><dd className="text-slate-800">{fmtDate(t.created_at)}</dd></div>
              {t.completed_at && <div className="flex justify-between gap-2"><dt className="text-slate-500">Completed</dt><dd className="text-slate-800">{fmtDate(t.completed_at)}</dd></div>}
            </dl>
          </Card>
          <Card title="Meetings" subtitle="Origin and carry-forwards">
            <ul className="flex flex-col gap-2">{data.meetings.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-2 text-xs">
                <Link to={`/meetings/${m.id}`} className="text-slate-800 font-medium hover:text-indigo-700 truncate">{m.title}</Link>
                <Badge tone={m.relationship_type === "origin" ? "indigo" : "cyan"}>{label(m.relationship_type)}</Badge>
              </li>))}</ul>
          </Card>
          <Card title="Related decisions">
            {data.decisions.length === 0 ? <p className="text-xs text-slate-400">None linked.</p> : (
              <ul className="flex flex-col gap-2.5">{data.decisions.map((d) => (
                <li key={d.id} className="text-xs"><div className="flex items-center gap-2"><Link to={`/knowledge?tab=decisions&decision=${d.id}`} className="font-mono font-bold text-indigo-600">{d.code}</Link><StatusBadge status={d.status} /></div>
                  <p className="text-slate-700 mt-0.5">{d.statement}</p></li>))}</ul>)}
          </Card>
        </div>
      </div>

      <Modal open={action !== null} onClose={() => setAction(null)} title={{ status: "Update status", owner: "Change owner", deadline: "Update deadline",
        blocker: "Record blocker", carry: "Carry forward to a meeting", close: "Close task", reopen: "Reopen task" }[action ?? "status"]}
        footer={<><Button onClick={() => setAction(null)}>Cancel</Button><Button variant="primary" loading={busy} disabled={!valid} onClick={submit}>Save</Button></>}>
        <div className="flex flex-col gap-3">
          {action === "status" && <>
            <Field label="Status"><select className={inputCls} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              {["open", "in_progress", "blocked"].map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></Field>
            <Field label={f.status === "blocked" ? "Blocker (required)" : "Note"}><textarea rows={3} className={textareaCls} value={f.note ?? ""} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
            <p className="text-[11px] text-slate-500">To complete or cancel, use Close (an outcome is required).</p>
          </>}
          {action === "owner" && <>
            <Field label="New owner"><select className={inputCls} value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })}>
              <option value="">Unassigned</option>{members.filter((m) => m.is_active).map((m) => <option key={m.id} value={m.id}>{m.name} — {m.role}</option>)}</select></Field>
            <Field label="Reason"><textarea rows={2} className={textareaCls} value={f.note ?? ""} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          </>}
          {action === "deadline" && <>
            <Field label="Due date"><input type="date" className={inputCls} value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} /></Field>
            <Field label="Deadline wording"><input className={inputCls} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></Field>
          </>}
          {action === "blocker" && <Field label="Blocker"><textarea rows={3} className={textareaCls} value={f.note ?? ""} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>}
          {action === "carry" && <>
            <Field label="Meeting" hint="Same task ID, owner and status; the meeting is added to the task's history. A task can be linked to a meeting only once.">
              <select className={inputCls} value={f.meeting ?? ""} onChange={(e) => setF({ ...f, meeting: e.target.value })}>
                <option value="">Choose a meeting…</option>
                {meetings?.map((m) => <option key={m.id} value={m.id} disabled={linked.has(m.id)}>{m.title} ({fmtDate(m.meeting_at)}){linked.has(m.id) ? " — already linked" : ""}</option>)}
              </select></Field>
            <Field label="Note"><input className={inputCls} value={f.note ?? ""} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          </>}
          {action === "close" && <>
            <Field label="Resolution"><select className={inputCls} value={f.resolution} onChange={(e) => setF({ ...f, resolution: e.target.value })}>
              <option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></Field>
            <Field label="Outcome (required)" hint="What was delivered or why it was cancelled. Stored permanently."><textarea rows={3} className={textareaCls} value={f.outcome ?? ""} onChange={(e) => setF({ ...f, outcome: e.target.value })} /></Field>
          </>}
          {action === "reopen" && <>
            <Callout tone="amber" icon={<Ban className="w-4 h-4" />}>Reopening is never automatic. The reason and previous outcome are kept in history.</Callout>
            <Field label="Reason (required)"><textarea rows={3} className={textareaCls} value={f.reason ?? ""} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
          </>}
        </div>
      </Modal>
    </>
  );
}

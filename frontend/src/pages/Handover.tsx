import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, ClipboardCopy, Sparkles } from "lucide-react";
import { BriefSection } from "../components/RefChips";
import { Badge, Button, Callout, Card, ConfirmDialog, EmptyState, ErrorState, Field, LoadingState, PageHeader, StatusBadge, Table, inputCls } from "../components/ui";
import { useApp } from "../lib/context";
import { api, useApi } from "../lib/api";
import { useToast } from "../lib/toast";
import { fmtDate, todayISO } from "../lib/format";
import type { Handover as H } from "../lib/types";

function HandoverView({ h, onChange }: { h: H; onChange: () => void }) {
  const { actorId, memberName, bump } = useApp();
  const toast = useToast();
  const [sel, setSel] = useState<Record<number, boolean>>({});
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => setSel(Object.fromEntries(h.tasks.map((t) => [t.task.id, t.selected]))), [h]);
  const brief = h.brief_json?.brief;
  const selectedCount = Object.values(sel).filter(Boolean).length;

  async function approve() {
    setBusy(true);
    try {
      const r = await api<H>(`/handovers/${h.id}/approve`, { body: { approved_by: actorId,
        selections: h.tasks.map((t) => ({ task_id: t.task.id, selected: !!sel[t.task.id] })) } });
      toast.success(`Handover approved. ${r.transferred_task_ids?.length ?? 0} task(s) transferred to ${h.to_member.name}.`);
      setConfirm(false); bump(); onChange();
    } catch (e) { toast.error(e); setConfirm(false); onChange(); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title={<div className="flex items-center gap-2 text-sm font-bold text-slate-900">{h.from_member.name}<ArrowRight className="w-4 h-4 text-slate-400" /><span className="text-indigo-600">{h.to_member.name}</span></div>}
        subtitle={`${fmtDate(h.start_date)} → ${fmtDate(h.end_date)}`}
        actions={<><StatusBadge status={h.status} />
          <Button size="sm" icon={<ClipboardCopy className="w-3.5 h-3.5" />} onClick={() => navigator.clipboard.writeText(h.brief_text ?? "").then(() => toast.success("Brief copied as Markdown."), toast.error)}>Copy brief</Button></>}>
        <div className="flex flex-col gap-5">
          <Callout tone={h.brief_json?.ai_status === "generated" ? "indigo" : "amber"} title={h.brief_json?.source}>
            {h.brief_json?.ai_status === "generated"
              ? "The task list below comes from the database, not the model. AI text cites records; verify before relying on it."
              : h.brief_json?.ai_message ?? "Brief assembled directly from RELAY records."}
          </Callout>
          {brief && <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div><h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Project overview</h4><p className="text-slate-700">{brief.project_overview}</p></div>
              <div><h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Current status</h4><p className="text-slate-700">{brief.current_status}</p></div>
              <div><h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Outstanding work</h4><p className="text-slate-700">{brief.outstanding_work_summary}</p></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <BriefSection title="Responsibilities being transferred" items={brief.responsibilities} />
              <BriefSection title="Important decisions" items={brief.important_decisions} />
              <BriefSection title="Blockers" items={brief.blockers} empty="No blocked work." />
              <BriefSection title="Relevant documents" items={brief.relevant_documents} />
              <BriefSection title="Recommended next actions" items={brief.next_actions} />
            </div>
          </>}
          {h.brief_json?.unassigned_tasks?.length > 0 && (
            <Callout tone="amber" title="Unassigned work in this project">
              {h.brief_json.unassigned_tasks.map((t: any) => <Link key={t.id} to={`/tasks/${t.id}`} className="underline mr-2">{t.title}</Link>)}
            </Callout>)}
        </div>
      </Card>

      <Card padded={false} title="Tasks in scope" subtitle="All unfinished tasks owned by the outgoing member (from SQL, not AI)">
        {h.tasks.length === 0 ? <EmptyState title={`${h.from_member.name} has no unfinished tasks in this project`} /> : (
          <Table head={["Transfer", "Task", "Status", "Due", "Latest blocker", "Result"]}>
            {h.tasks.map(({ task: t, transferred_at }) => {
              const row = h.brief_json?.tasks?.find((x: any) => x.id === t.id);
              return (
                <tr key={t.id}>
                  <td className="py-3 px-5"><input type="checkbox" aria-label={`Transfer ${t.title}`} disabled={h.status !== "draft"} checked={!!sel[t.id]} onChange={(e) => setSel({ ...sel, [t.id]: e.target.checked })} /></td>
                  <td className="py-3 px-4"><Link to={`/tasks/${t.id}`} className="font-semibold text-slate-900 hover:text-indigo-700">{t.title}</Link><p className="text-[11px] text-slate-500">Now owned by {t.owner_name ?? "nobody"}</p></td>
                  <td className="py-3 px-4"><StatusBadge status={t.status} /></td>
                  <td className={`py-3 px-4 whitespace-nowrap ${t.is_overdue ? "text-rose-600 font-semibold" : "text-slate-600"}`}>{fmtDate(t.due_at)}</td>
                  <td className="py-3 px-4 text-slate-600 max-w-xs">{row?.latest_blocker ?? "—"}</td>
                  <td className="py-3 px-4">{transferred_at ? <Badge tone="cyan">Transferred {fmtDate(transferred_at)}</Badge> : h.status === "draft" ? <span className="text-slate-400">Pending</span> : <span className="text-slate-400">Not selected</span>}</td>
                </tr>);
            })}
          </Table>)}
        {h.status === "draft" && h.tasks.length > 0 && (
          <div className="p-4 border-t border-surface-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-xs text-slate-600">Deadlines are not changed. Completed tasks are never transferred. All selected transfers succeed together or none do.</p>
            <Button variant="primary" disabled={selectedCount === 0} onClick={() => setConfirm(true)}>Approve transfer of {selectedCount} task(s)…</Button>
          </div>)}
        {h.status === "approved" && <p className="p-4 border-t border-surface-border text-xs text-slate-600">Approved by {h.approved_by_name} on {fmtDate(h.approved_at, true)}.</p>}
      </Card>
      <ConfirmDialog open={confirm} loading={busy} onCancel={() => setConfirm(false)} onConfirm={approve} title="Approve handover" confirmLabel="Transfer ownership"
        message={<>As <b>{memberName(actorId)}</b>, transfer {selectedCount} task(s) from <b>{h.from_member.name}</b> to <b>{h.to_member.name}</b>? Each transfer is recorded in task history. If any task changed since this draft (completed or reassigned), nothing is transferred.</>} />
    </div>
  );
}

export function Handover() {
  const { project, members, actorId, revision, bump } = useApp();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const { data: list, loading, error, reload } = useApi<H[]>(`/handovers?project_id=${project!.id}&r=${revision}`);
  const selectedId = params.get("id") ? Number(params.get("id")) : list?.[0]?.id;
  const current = list?.find((h) => h.id === selectedId) ?? null;
  const [f, setF] = useState({ from: "", to: "", start: todayISO(), end: "" });
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true);
    try {
      const h = await api<H>("/handovers/generate", { body: { project_id: project!.id, from_member_id: Number(f.from), to_member_id: Number(f.to),
        start_date: f.start, end_date: f.end || null, created_by: actorId } });
      toast.success(`Draft handover created with ${h.tasks.length} task(s).`);
      bump(); await reload(); setParams({ id: String(h.id) });
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Handover Copilot" description="Transfer responsibilities with full context. The database decides what is in scope; a manager approves every transfer." />
      <Card title="Prepare a handover">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <Field label="Outgoing" htmlFor="ho-from"><select id="ho-from" className={inputCls} value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })}>
            <option value="">Choose…</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
          <Field label="Incoming" htmlFor="ho-to"><select id="ho-to" className={inputCls} value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })}>
            <option value="">Choose…</option>{members.filter((m) => m.is_active && String(m.id) !== f.from).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
          <Field label="Start" htmlFor="ho-start"><input id="ho-start" type="date" className={inputCls} value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
          <Field label="End" htmlFor="ho-end"><input id="ho-end" type="date" className={inputCls} value={f.end} min={f.start} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
          <Button variant="gradient" loading={busy} disabled={!f.from || !f.to || f.from === f.to} onClick={generate} icon={<Sparkles className="w-4 h-4" />}>Generate draft</Button>
        </div>
      </Card>
      {loading && !list ? <LoadingState /> : error ? <ErrorState error={error} onRetry={reload} /> : list?.length === 0 ? (
        <Card><EmptyState title="No handovers yet" description="Choose an outgoing and incoming member to prepare one." /></Card>) : (
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
          <Card title="Handovers" padded={false} className="xl:col-span-1 h-fit">
            <ul className="divide-y divide-surface-border">
              {list?.map((h) => (
                <li key={h.id}><button onClick={() => setParams({ id: String(h.id) })}
                  className={`w-full text-left px-4 py-3 text-xs hover:bg-slate-50 ${h.id === selectedId ? "bg-indigo-50/50" : ""}`}>
                  <div className="flex items-center justify-between gap-2"><span className="font-semibold text-slate-800">{h.from_member.name} → {h.to_member.name}</span><StatusBadge status={h.status} /></div>
                  <p className="text-slate-500 mt-0.5">{h.tasks.length} task(s) · created {fmtDate(h.created_at)}</p>
                </button></li>))}
            </ul>
          </Card>
          <div className="xl:col-span-3">{current && <HandoverView h={current} onChange={reload} />}</div>
        </div>
      )}
    </>
  );
}

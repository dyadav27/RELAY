import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, FileText, RefreshCw, Sparkles } from "lucide-react";
import { DecisionConflictPanel } from "../components/DecisionConflictPanel";
import { EventTimelineItem } from "../components/EventText";
import { ExtractionReview } from "../components/ExtractionReview";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, IntegrityBadge, LoadingState, PageHeader, Quote, StatusBadge, Table, Timeline, textareaCls } from "../components/ui";
import { useApp } from "../lib/context";
import { api, useApi } from "../lib/api";
import { useToast } from "../lib/toast";
import { fmtDate, label } from "../lib/format";
import type { MeetingDetail as MD } from "../lib/types";

const TABS = ["overview", "notes", "review", "outcomes", "integrity", "activity"] as const;
const TAB_LABEL: Record<string, string> = { overview: "Overview", notes: "Original notes", review: "AI extraction",
  outcomes: "Blockers & questions", integrity: "Decision integrity", activity: "Activity" };

export function MeetingDetail() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") ?? "overview") as (typeof TABS)[number];
  const { revision, bump } = useApp();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<MD>(`/meetings/${id}?r=${revision}`);
  const [extracting, setExtracting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [notes, setNotes] = useState("");

  if (loading && !data) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const m = data.meeting;
  const draft = m.extraction_draft;
  const setTab = (t: string) => setParams({ tab: t });

  async function extract() {
    setExtracting(true);
    try {
      await api(`/meetings/${m.id}/extract`, { method: "POST" });
      toast.success("Extraction draft ready for review. Decision integrity analysis ran as well.");
      bump(); await reload(); setTab("review");
    } catch (e) { toast.error(e); await reload(); } finally { setExtracting(false); }
  }
  async function analyze() {
    setAnalyzing(true);
    try { await api(`/decisions/analyze`, { body: { meeting_id: m.id } }); toast.success("Decision integrity analysis re-run."); bump(); await reload(); }
    catch (e) { toast.error(e); } finally { setAnalyzing(false); }
  }
  async function saveNotes() {
    try { await api(`/meetings/${m.id}`, { method: "PATCH", body: { raw_notes: notes } }); toast.success("Notes updated. Re-run extraction to refresh the draft."); setEditing(false); await reload(); }
    catch (e) { toast.error(e); }
  }

  const pendingAlerts = data.alerts.filter((a) => a.status === "pending");
  const integrity = draft?.integrity;

  return (
    <>
      <Link to="/meetings" className="text-xs text-slate-500 hover:text-indigo-700 flex items-center gap-1 -mb-3"><ArrowLeft className="w-3.5 h-3.5" />Meetings</Link>
      <PageHeader title={m.title}
        badge={<><StatusBadge status={m.extraction_status} /><IntegrityBadge integrity={m.integrity} /></>}
        description={<>{fmtDate(m.meeting_at, true)} · {data.project.name} · MTG-{m.id}</>}
        actions={m.extraction_status !== "approved" && (
          <Button variant="gradient" loading={extracting} onClick={extract} icon={<Sparkles className="w-4 h-4" />}>
            {m.extraction_status === "pending" ? "Run AI extraction" : m.extraction_status === "failed" ? "Retry extraction" : "Re-run extraction"}
          </Button>)} />

      {m.extraction_status === "failed" && <Callout tone="rose" title="The last extraction attempt failed">Original notes are preserved. Check AI configuration and retry.</Callout>}
      {m.extraction_status === "extracted" && tab !== "review" && (
        <Callout tone="amber" title="AI draft awaiting human review">Decisions and tasks are not official until approved.{" "}
          <button className="underline font-semibold" onClick={() => setTab("review")}>Review now</button></Callout>)}

      <div className="flex gap-1 border-b border-surface-border overflow-x-auto" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`px-3 py-2 text-xs font-semibold whitespace-nowrap border-b-2 -mb-px ${tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {TAB_LABEL[t]}{t === "integrity" && pendingAlerts.length > 0 && <span className="ml-1.5 px-1.5 rounded-full bg-amber-100 text-amber-800">{pendingAlerts.length}</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 flex flex-col gap-6">
            <Card title="Summary">{m.summary ? <p className="text-xs text-slate-700 leading-relaxed">{m.summary}</p>
              : <p className="text-xs text-slate-400">{draft ? "Draft summary available in the AI extraction tab (not yet approved)." : "No summary yet. Run extraction."}</p>}</Card>
            <Card title="Decisions recorded from this meeting" padded={false}>
              {data.decisions.length === 0 ? <EmptyState title="No decisions recorded" /> : (
                <Table head={["ID", "Statement", "Status", "Approved by"]}>
                  {data.decisions.map((d) => (
                    <tr key={d.id}><td className="py-3 px-5 font-mono text-indigo-600 font-bold">{d.code}</td>
                      <td className="py-3 px-4 text-slate-700">{d.statement}</td><td className="py-3 px-4"><StatusBadge status={d.status} /></td>
                      <td className="py-3 px-4 text-slate-600">{d.approved_by_name ?? "—"}</td></tr>))}
                </Table>)}
            </Card>
            <Card title="Action items & linked tasks" padded={false}>
              {data.tasks.length === 0 ? <EmptyState title="No tasks linked yet" /> : (
                <Table head={["Task", "Link", "Owner", "Status", "Due"]}>
                  {data.tasks.map((t) => (
                    <tr key={t.id}><td className="py-3 px-5"><Link to={`/tasks/${t.id}`} className="font-semibold text-slate-900 hover:text-indigo-700">{t.title}</Link></td>
                      <td className="py-3 px-4"><Badge tone={t.relationship_type === "origin" ? "indigo" : "cyan"}>{label(t.relationship_type ?? "")}</Badge></td>
                      <td className="py-3 px-4 text-slate-600">{t.owner_name ?? <span className="text-amber-700">Unassigned</span>}</td>
                      <td className="py-3 px-4"><StatusBadge status={t.status} /></td>
                      <td className={`py-3 px-4 whitespace-nowrap ${t.is_overdue ? "text-rose-600 font-semibold" : "text-slate-600"}`}>{fmtDate(t.due_at)}</td></tr>))}
                </Table>)}
            </Card>
          </div>
          <div className="flex flex-col gap-6">
            <Card title="Participants">
              <ul className="flex flex-col gap-1.5 text-xs">{m.participants.map((p) => (
                <li key={p.member_id} className="flex justify-between"><span className="text-slate-800 font-medium">{p.name}</span><Badge tone={p.attendance_status === "absent" ? "slate" : "cyan"}>{p.attendance_status}</Badge></li>))}</ul>
            </Card>
            {m.agenda && <Card title="Agenda"><p className="text-xs text-slate-700 whitespace-pre-wrap">{m.agenda}</p></Card>}
            <Card title="Related documents" subtitle="By shared terms">
              {data.related_documents.length === 0 ? <p className="text-xs text-slate-400">None found.</p> : (
                <ul className="flex flex-col gap-1.5">{data.related_documents.map((d) => (
                  <li key={d.id}><Link to={`/knowledge?tab=documents&document=${d.id}`} className="text-xs text-indigo-700 hover:underline flex items-center gap-1.5"><FileText className="w-3.5 h-3.5" />{d.title} v{d.version_number}</Link></li>))}</ul>)}
            </Card>
          </div>
        </div>
      )}

      {tab === "notes" && (
        <Card title="Original notes" subtitle={`SHA-256 ${m.source_hash.slice(0, 12)}…`}
          actions={m.extraction_status !== "approved" && !editing ? <Button size="sm" onClick={() => { setNotes(m.raw_notes ?? ""); setEditing(true); }}>Edit notes</Button> : undefined}>
          {editing ? (
            <div className="flex flex-col gap-3">
              <Callout tone="amber">Editing the notes invalidates any existing extraction draft (approval is blocked until you re-extract).</Callout>
              <textarea rows={16} className={textareaCls} value={notes} onChange={(e) => setNotes(e.target.value)} />
              <div className="flex justify-end gap-2"><Button onClick={() => setEditing(false)}>Cancel</Button><Button variant="primary" onClick={saveNotes}>Save notes</Button></div>
            </div>
          ) : <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{m.raw_notes}</pre>}
        </Card>
      )}

      {tab === "review" && (
        <Card title="AI extraction">
          {!draft ? <EmptyState title="No extraction yet" description="Run AI extraction to draft a summary, decisions, tasks, blockers and open questions."
            action={<Button variant="gradient" loading={extracting} onClick={extract}>Run AI extraction</Button>} />
            : m.extraction_status === "approved" ? (
              <div className="flex flex-col gap-3 text-xs">
                <Callout tone="cyan" title="This extraction has been approved">The approved summary, decisions and tasks are shown in the Overview tab. The original AI draft is kept below for audit.</Callout>
                <p className="text-slate-500">Draft model: <span className="font-mono">{draft.model}</span> · generated {fmtDate(draft.generated_at, true)}</p>
                <p className="text-slate-700">{draft.summary}</p>
              </div>
            ) : <ExtractionReview key={draft.generated_at} meeting={m} onApproved={() => { reload(); setTab("overview"); }} />}
        </Card>
      )}

      {tab === "outcomes" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card title="Blockers">
            {!draft?.blockers?.length ? <p className="text-xs text-slate-400">None extracted.</p> : (
              <ul className="flex flex-col gap-3">{draft.blockers.map((b: any, i: number) => (
                <li key={i} className="flex flex-col gap-1"><p className="text-xs font-semibold text-slate-800">{b.description}</p><Quote>{b.evidence}</Quote></li>))}</ul>)}
          </Card>
          <Card title="Unresolved questions">
            {!draft?.unresolved_questions?.length ? <p className="text-xs text-slate-400">None extracted.</p> : (
              <ul className="flex flex-col gap-3">{draft.unresolved_questions.map((q: any, i: number) => (
                <li key={i} className="flex flex-col gap-1"><p className="text-xs font-semibold text-slate-800">{q.question}</p>{q.evidence && <Quote>{q.evidence}</Quote>}</li>))}</ul>)}
          </Card>
        </div>
      )}

      {tab === "integrity" && (
        <div className="flex flex-col gap-6">
          <Card title="Decision integrity analysis" actions={draft && <Button size="sm" loading={analyzing} onClick={analyze} icon={<RefreshCw className="w-3.5 h-3.5" />}>Re-run analysis</Button>}>
            {!integrity ? <p className="text-xs text-slate-500">Runs automatically after AI extraction, comparing this meeting with approved decisions of the same project only.</p>
              : integrity.status === "failed" ? <Callout tone="rose" title="Analysis failed">{integrity.message}</Callout>
              : <p className="text-xs text-slate-600">Compared with {integrity.historical_decisions_checked ?? 0} approved decision(s) {integrity.analyzed_at ? `on ${fmtDate(integrity.analyzed_at, true)}` : ""}.
                {" "}{integrity.consistent?.length ?? 0} consistent, {integrity.alert_ids?.length ?? 0} flagged{integrity.note ? `. ${integrity.note}` : ""}</p>}
          </Card>
          {pendingAlerts.length > 0 && <DecisionConflictPanel alerts={pendingAlerts} onResolved={reload} />}
          {data.alerts.filter((a) => a.status !== "pending").map((a) => (
            <Card key={a.id} title={`${a.code} · ${label(a.classification)}`} actions={<StatusBadge status={a.status} />}>
              <p className="text-xs text-slate-700">{a.proposed_statement}</p>
              <p className="text-[11px] text-slate-500 mt-1">Resolved by {a.resolved_by_name} · {fmtDate(a.resolved_at, true)}{a.resolution_note ? ` · “${a.resolution_note}”` : ""}</p>
            </Card>))}
        </div>
      )}

      {tab === "activity" && (
        <Card title="Task activity linked to this meeting">
          {data.activity.length === 0 ? <EmptyState title="No activity yet" /> : <Timeline>{data.activity.map((e) => <EventTimelineItem key={e.id} e={e} showTask />)}</Timeline>}
        </Card>
      )}
    </>
  );
}

import { Link } from "react-router-dom";
import { ArrowRight, BadgeCheck, CheckSquare, ShieldCheck, Sparkles } from "lucide-react";
import { DecisionConflictPanel } from "../components/DecisionConflictPanel";
import { EventTimelineItem } from "../components/EventText";
import { useUiActions } from "../components/Layout";
import { Badge, Button, Card, EmptyState, ErrorState, IntegrityBadge, LoadingState, MetricCard, PageHeader, StatusBadge, Table, Timeline } from "../components/ui";
import { useApp } from "../lib/context";
import { useApi } from "../lib/api";
import { fmtDate, relTime } from "../lib/format";
import type { Dashboard } from "../lib/types";

function HandoverSummary({ h }: { h: Dashboard["latest_handover"] }) {
  if (!h) return <EmptyState title="No handovers yet" description="Prepare one when someone goes on leave or changes role."
    action={<Link to="/handover"><Button size="sm">Open Handover Copilot</Button></Link>} />;
  const total = h.tasks.length;
  const selected = h.tasks.filter((t) => t.selected).length;
  const transferred = h.tasks.filter((t) => t.transferred_at).length;
  const blocked = h.tasks.filter((t) => t.task.status === "blocked").length;
  const pct = total ? Math.round(((h.status === "approved" ? transferred : 0) / total) * 100) : 0;
  return (
    <div className="flex flex-col gap-3">
      <div className="p-4 rounded-lg bg-slate-50 border border-surface-border flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">Responsibility handover</span>
          <StatusBadge status={h.status} />
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-800">
          <span className="font-semibold">{h.from_member.name}</span>
          <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-semibold text-indigo-600">{h.to_member.name}</span>
          <span className="text-slate-400 ml-auto font-mono text-[11px]">{fmtDate(h.start_date)} → {fmtDate(h.end_date)}</span>
        </div>
        <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="bg-gradient-to-r from-indigo-500 to-cyan-500 h-full rounded-full" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-xs text-slate-500">
          <strong className="text-slate-800 font-semibold">{transferred} of {total}</strong> tasks transferred
          {h.status === "draft" && <> · {selected} selected, awaiting manager approval</>}
        </p>
      </div>
      {h.status === "draft" && (
        <div className="p-4 rounded-lg bg-amber-50/60 border border-amber-200 flex flex-col gap-2">
          <span className="text-xs font-semibold text-amber-800">Approval needed</span>
          <p className="text-xs text-slate-600">
            {total} unfinished task(s) of {h.from_member.name}{blocked ? `, including ${blocked} blocked,` : ""} are waiting to move to {h.to_member.name}.
            Ownership changes only after approval.
          </p>
          <Link to={`/handover?id=${h.id}`}>
            <Button size="sm" className="w-full border-amber-200">Review handover</Button>
          </Link>
        </div>
      )}
    </div>
  );
}

export function Overview() {
  const { project, revision } = useApp();
  const { openCatchUp, openLogMeeting } = useUiActions();
  const { data, error, loading, reload } = useApi<Dashboard>(`/dashboard?project_id=${project!.id}&r=${revision}`);

  if (loading && !data) return <LoadingState text="Loading command center…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  const m = data.metrics;

  return (
    <>
      <PageHeader title="Command Center"
        badge={data.is_demo_data ? <Badge tone="amber" dot>Synthetic demo data</Badge> : undefined}
        description={<>Project: <span className="font-semibold text-slate-700">{data.project.name}</span><span className="mx-2 text-slate-300">•</span>
          Workspace: {data.workspace.name}<span className="mx-2 text-slate-300">•</span>Loaded {relTime(data.generated_at)}</>}
        actions={<>
          <Button onClick={openLogMeeting} icon={<span className="w-2 h-2 rounded-full bg-indigo-500" />}>Log meeting notes</Button>
          <Button variant="gradient" onClick={openCatchUp} icon={<Sparkles className="w-4 h-4" />}>New catch-up brief</Button>
        </>} />

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Open tasks" value={m.open_tasks} icon={<CheckSquare className="w-4 h-4" />}
          footnote={<><strong className="text-slate-800 font-semibold">{m.in_progress}</strong> in progress • {m.blocked} blocked • {m.unassigned} unassigned</>} />
        <MetricCard label="Overdue tasks" value={m.overdue} tone={m.overdue ? "rose" : "slate"}
          badge={m.overdue ? <Badge tone="rose" dot>Past deadline</Badge> : undefined}
          footnote="Unfinished tasks whose due date has passed" />
        <MetricCard label="Completed (last 7d)" value={m.completed_last_7d} tone="indigo"
          footnote={<>{m.completed_total} completed in total, each with a recorded outcome</>} />
        <MetricCard label="Decision reviews" value={m.pending_decision_alerts} tone={m.pending_decision_alerts ? "amber" : "slate"}
          badge={m.pending_decision_alerts ? <Badge tone="amber">Needs review</Badge> : undefined}
          footnote="Discussions that diverge from approved decisions" />
      </section>

      {data.pending_alerts.length > 0 ? <DecisionConflictPanel alerts={data.pending_alerts} onResolved={reload} /> : (
        <Card><div className="flex items-center gap-3 text-xs text-slate-600">
          <ShieldCheck className="w-5 h-5 text-cyan-600" />
          No pending decision integrity reviews. New meetings are compared with approved decisions after extraction.
        </div></Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 flex flex-col gap-6">
          <Card padded={false} title="Recent meetings" subtitle={`${m.meetings} logged`}
            actions={<Link to="/meetings" className="text-xs text-indigo-600 hover:text-indigo-700 font-semibold flex items-center gap-1">View all <ArrowRight className="w-3.5 h-3.5" /></Link>}>
            <Table head={["Meeting", "Extraction", "Decision integrity", "Key decision", ""]}
              empty={data.recent_meetings.length === 0 ? <EmptyState title="No meetings yet" action={<Button size="sm" onClick={openLogMeeting}>Log meeting</Button>} /> : null}>
              {data.recent_meetings.map((mt) => (
                <tr key={mt.id} className="hover:bg-slate-50/50 transition-colors">
                  <td className="py-3.5 px-5">
                    <Link to={`/meetings/${mt.id}`} className="font-semibold text-slate-900 hover:text-indigo-700">{mt.title}</Link>
                    <p className="text-[11px] text-slate-500">{fmtDate(mt.meeting_at)} • {mt.participants.length} participants</p>
                  </td>
                  <td className="py-3.5 px-4"><StatusBadge status={mt.extraction_status} /></td>
                  <td className="py-3.5 px-4"><IntegrityBadge integrity={mt.integrity} /></td>
                  <td className="py-3.5 px-4 text-slate-600 max-w-xs">
                    {mt.key_decision ? <><span className="font-mono text-[10px] text-indigo-600 font-bold mr-1">{mt.key_decision.code}</span>{mt.key_decision.statement}</>
                      : <span className="text-slate-400">{mt.extraction_status === "approved" ? "No decisions recorded" : "Awaiting review"}</span>}
                  </td>
                  <td className="py-3.5 px-5 text-right whitespace-nowrap">
                    <Link to={`/meetings/${mt.id}`}><Button size="sm">{mt.extraction_status === "pending" ? "Extract" : mt.extraction_status === "extracted" ? "Review" : "View"}</Button></Link>
                  </td>
                </tr>
              ))}
            </Table>
          </Card>

          <Card title="Recent approved decisions" subtitle="Decision ledger"
            actions={<Link to="/knowledge?tab=decisions" className="text-xs text-indigo-600 hover:text-indigo-700 font-semibold flex items-center gap-1">Full ledger <ArrowRight className="w-3.5 h-3.5" /></Link>}>
            {data.recent_decisions.length === 0 ? <EmptyState title="No approved decisions yet" /> : (
              <div className="flex flex-col gap-3">
                {data.recent_decisions.map((d) => (
                  <div key={d.id} className="p-4 rounded-lg bg-slate-50 hover:bg-slate-100/70 border border-surface-border transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex flex-col gap-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-indigo-600">{d.code}</span>
                        <StatusBadge status={d.status} />
                        {d.meeting_title && <Link to={`/meetings/${d.meeting_id}`} className="px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-600 text-[11px] font-medium hover:text-indigo-700">{d.meeting_title}</Link>}
                      </div>
                      <h4 className="text-xs font-semibold text-slate-900 pt-0.5">{d.statement}</h4>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 text-right">
                      <div className="flex flex-col">
                        <span className="text-xs text-slate-900 font-semibold">{d.approved_by_name}</span>
                        <span className="text-[11px] text-slate-500">Approved {relTime(d.approved_at)}</span>
                      </div>
                      <BadgeCheck className={`w-5 h-5 ${d.status === "active" ? "text-cyan-600" : "text-slate-300"}`} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="lg:col-span-4 flex flex-col gap-6">
          <Card title="Continuity handover" actions={<Link to="/handover" className="text-xs text-indigo-600 font-semibold">Open</Link>}>
            <HandoverSummary h={data.latest_handover} />
          </Card>
          <Card title="Recent task activity" subtitle="From the task event log">
            {data.activity.length === 0 ? <EmptyState title="No activity yet" /> : (
              <Timeline>{data.activity.map((e) => <EventTimelineItem key={e.id} e={e} showTask />)}</Timeline>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRightLeft, BadgeCheck, ChevronLeft, ChevronRight, GitBranch, ListChecks, MessageSquareWarning, User } from "lucide-react";
import { Badge, Button, ConfirmDialog, Field, StatusBadge, textareaCls } from "./ui";
import { useApp } from "../lib/context";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import { fmtDate } from "../lib/format";
import type { Alert } from "../lib/types";

const HEADLINE: Record<string, string> = {
  proposal: "Proposal to change an approved decision",
  potential_conflict: "Potential conflict with an approved decision",
  conditional_change: "Conditional change to an approved decision",
  revisit: "Team plans to revisit an approved decision",
  explicit_replacement: "Discussion states an approved decision is replaced",
};

type Action = "confirm_change" | "mark_proposal" | "dismiss";

/** The signature Decision Integrity Engine view: historical decision vs new discussion, with human review. */
export function DecisionConflictPanel({ alerts, onResolved, compact = false }:
  { alerts: Alert[]; onResolved: () => void; compact?: boolean }) {
  const [idx, setIdx] = useState(0);
  const [action, setAction] = useState<Action | null>(null);
  const [statement, setStatement] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const { actorId, memberName, bump } = useApp();
  const toast = useToast();
  if (alerts.length === 0) return null;
  const a = alerts[Math.min(idx, alerts.length - 1)];
  const old = a.existing_decision;

  function open(act: Action) {
    setAction(act);
    setStatement(a.proposed_statement);
    setNote("");
  }

  async function resolve() {
    if (!action) return;
    setBusy(true);
    try {
      const res = await api<any>(`/decision-alerts/${a.id}/resolve`, { body: {
        action, actor_id: actorId, note: note.trim() || null,
        statement: action !== "dismiss" && statement.trim() !== a.proposed_statement ? statement.trim() : null } });
      const msg = action === "confirm_change"
        ? `${res.new_decision.code} is now active; ${old.code} superseded. ${res.tasks_flagged_for_review.length} task(s) flagged for review.`
        : action === "mark_proposal" ? `Recorded ${res.new_decision.code} as a proposal. ${old.code} remains active.` : "Alert dismissed.";
      toast.success(msg);
      setAction(null);
      setIdx(0);
      bump();
      onResolved();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return (
    <section className="bg-white rounded-xl p-5 lg:p-6 border border-surface-border shadow-sm flex flex-col gap-4 relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-500 via-indigo-500 to-cyan-500" />
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="px-2.5 py-0.5 rounded-md bg-amber-100 text-amber-900 font-bold text-[11px] uppercase tracking-wider border border-amber-200">
            Decision integrity review
          </span>
          <span className="font-mono text-xs text-slate-500 font-medium">{a.code}</span>
          <StatusBadge status={a.classification} />
        </div>
        {alerts.length > 1 && (
          <div className="flex items-center gap-1 text-xs text-slate-500">
            <button aria-label="Previous alert" className="p-1 rounded hover:bg-slate-100 disabled:opacity-40" disabled={idx === 0} onClick={() => setIdx(idx - 1)}><ChevronLeft className="w-4 h-4" /></button>
            <span className="font-mono">{idx + 1} / {alerts.length}</span>
            <button aria-label="Next alert" className="p-1 rounded hover:bg-slate-100 disabled:opacity-40" disabled={idx >= alerts.length - 1} onClick={() => setIdx(idx + 1)}><ChevronRight className="w-4 h-4" /></button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <h2 className="text-base font-bold text-slate-900">{HEADLINE[a.classification] ?? "Decision drift detected"}</h2>
        <p className="text-xs text-slate-600">
          During <Link to={`/meetings/${a.meeting.id}`} className="font-semibold text-slate-900 hover:text-indigo-700">“{a.meeting.title}”</Link>{" "}
          ({fmtDate(a.meeting.meeting_at)}), the discussion diverged from an approved decision. Nothing has been changed; a human decides.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-200/80 flex flex-col justify-between gap-3">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <BadgeCheck className="w-4 h-4 text-indigo-600" />
                <span className="text-xs font-bold text-indigo-900">Approved decision {old.code}</span>
              </div>
              <span className="text-[11px] text-slate-500">{fmtDate(old.approved_at)}</span>
            </div>
            <p className="text-xs text-slate-800 leading-relaxed font-medium">{old.statement}</p>
            {a.old_evidence && <p className="text-[11px] text-slate-500 italic leading-relaxed">Source: “{a.old_evidence}”</p>}
          </div>
          <div className="flex items-center justify-between gap-2 text-slate-500 font-mono text-[11px]">
            <span className="flex items-center gap-1"><User className="w-3 h-3" />Approved by {old.approved_by_name ?? "—"}</span>
            {old.meeting_id && <Link className="hover:text-indigo-700" to={`/meetings/${old.meeting_id}`}>{old.meeting_title}</Link>}
          </div>
        </div>
        <div className="bg-amber-50/60 rounded-lg p-4 border border-amber-200 flex flex-col justify-between gap-3">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <MessageSquareWarning className="w-4 h-4 text-amber-700" />
                <span className="text-xs font-bold text-amber-900">New discussion</span>
              </div>
              <span className="text-[11px] text-slate-500">{fmtDate(a.meeting.meeting_at)}</span>
            </div>
            <p className="text-xs text-slate-800 leading-relaxed font-medium">{a.proposed_statement}</p>
            {a.new_evidence ? <p className="text-[11px] text-slate-600 italic leading-relaxed">Notes: “{a.new_evidence}”</p>
              : <p className="text-[11px] text-amber-700">No verbatim quote could be matched in the notes; read the original notes.</p>}
          </div>
          <div className="flex items-center gap-1 text-amber-700 font-mono text-[11px]">
            <ArrowRightLeft className="w-3 h-3" /> Not approved — pending human review
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg p-3.5 border border-indigo-100 bg-indigo-50/40 flex gap-2.5">
          <GitBranch className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-indigo-800">AI explanation (verify against sources)</p>
            <p className="text-xs text-slate-700 leading-relaxed mt-1">{a.explanation}</p>
          </div>
        </div>
        <div className="rounded-lg p-3.5 border border-surface-border bg-slate-50 flex gap-2.5">
          <ListChecks className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">Potentially affected work</p>
            {a.affected_tasks.length === 0 ? <p className="text-xs text-slate-500 mt-1">No linked open tasks identified.</p> : (
              <ul className="mt-1 flex flex-col gap-1">
                {a.affected_tasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-2 text-xs">
                    <Link to={`/tasks/${t.id}`} className="text-slate-800 font-medium hover:text-indigo-700 truncate">{t.title}</Link>
                    <span className="text-slate-400 whitespace-nowrap">{t.owner_name ?? "unassigned"}</span>
                    <StatusBadge status={t.status} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {!compact && (
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-slate-50 rounded-lg p-3.5 border border-surface-border">
          <div className="flex items-center gap-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <p className="text-xs text-slate-700">
              Confirming creates a new active decision, marks {old.code} as superseded and keeps both source meetings in the lineage.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <Button size="sm" variant="primary" onClick={() => open("confirm_change")}>Confirm new decision</Button>
            <Button size="sm" onClick={() => open("mark_proposal")}>Record as proposal</Button>
            <Button size="sm" variant="ghost" onClick={() => open("dismiss")}>Dismiss</Button>
          </div>
        </div>
      )}
      {compact && (
        <div className="flex items-center gap-2 flex-wrap">
          <Button size="sm" variant="primary" onClick={() => open("confirm_change")}>Confirm new decision</Button>
          <Button size="sm" onClick={() => open("mark_proposal")}>Record as proposal</Button>
          <Button size="sm" variant="ghost" onClick={() => open("dismiss")}>Dismiss</Button>
        </div>
      )}

      <ConfirmDialog open={action !== null} loading={busy} onCancel={() => setAction(null)} onConfirm={resolve}
        danger={action === "confirm_change"}
        title={action === "confirm_change" ? `Supersede ${old.code}?` : action === "mark_proposal" ? "Record as a proposal" : "Dismiss this alert?"}
        confirmLabel={action === "confirm_change" ? "Approve change" : action === "mark_proposal" ? "Record proposal" : "Dismiss"}
        message={action === "confirm_change"
          ? <>You are approving a change to an active decision as <b>{memberName(actorId)}</b>. {old.code} will be marked superseded (not deleted) and {a.affected_tasks.length} task(s) will be flagged for review.</>
          : action === "mark_proposal" ? <>A proposed decision will be recorded and linked to {old.code}. {old.code} stays active.</>
          : <>The alert will be closed without changes. {old.code} stays active.</>}>
        {action !== "dismiss" && (
          <Field label="Decision statement" htmlFor="dc-statement">
            <textarea id="dc-statement" rows={3} className={textareaCls} value={statement} onChange={(e) => setStatement(e.target.value)} />
          </Field>
        )}
        <Field label="Reason / note" htmlFor="dc-note">
          <textarea id="dc-note" rows={2} className={textareaCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional, stored with the decision lineage" />
        </Field>
        <Badge tone="slate">Recorded as {memberName(actorId)} (demo identity)</Badge>
      </ConfirmDialog>
    </section>
  );
}

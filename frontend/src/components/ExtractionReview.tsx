import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Quote as QuoteIcon } from "lucide-react";
import { Badge, Button, Callout, ConfirmDialog, Field, StatusBadge, inputCls, textareaCls } from "./ui";
import { useApp } from "../lib/context";
import { api, useApi } from "../lib/api";
import { useToast } from "../lib/toast";
import type { Meeting, Task } from "../lib/types";

type DecisionRow = { statement: string; evidence: string; status: "active" | "proposed"; include: boolean; verified: boolean; kind: string };
type ItemRow = {
  action: "create" | "link" | "carry_forward" | "exclude"; existing_task_id: number | null; title: string;
  description: string; owner_id: number | null; due_at: string; deadline_text: string; priority: string;
  evidence: string; flags: string[]; suggested_owner_name: string | null; owner_resolution: string;
  owner_candidates: number[]; matches: { task_id: number; title: string; status: string; score: number }[];
};

const RESOLUTION_TEXT: Record<string, string> = {
  matched: "matched to participant", ambiguous: "ambiguous — choose the owner", not_a_participant: "named person is not a participant",
  not_in_notes: "model suggested a name not in the notes; ignored", none: "no owner in notes",
};

export function ExtractionReview({ meeting, onApproved }: { meeting: Meeting; onApproved: () => void }) {
  const draft = meeting.extraction_draft;
  const { members, memberName, actorId, bump } = useApp();
  const toast = useToast();
  const { data: tasks } = useApi<Task[]>(`/tasks?project_id=${meeting.project_id}`);
  const participantIds = meeting.participants.map((p) => p.member_id);
  const [summary, setSummary] = useState<string>(draft.summary);
  const [decisions, setDecisions] = useState<DecisionRow[]>(() => [
    ...draft.confirmed_decisions.map((d: any) => ({ statement: d.statement, evidence: d.evidence, status: "active", include: true, verified: d.evidence_verified, kind: "confirmed" })),
    ...draft.proposed_decisions.map((d: any) => ({ statement: d.statement, evidence: d.evidence, status: "proposed", include: true, verified: d.evidence_verified, kind: "proposed" })),
  ]);
  const [items, setItems] = useState<ItemRow[]>(() => draft.action_items.map((a: any) => ({
    action: a.suggested_action, existing_task_id: a.existing_task_matches?.[0]?.task_id ?? null, title: a.title,
    description: a.description ?? "", owner_id: a.owner_id, due_at: a.due_date ?? "", deadline_text: a.deadline_text ?? "",
    priority: "medium", evidence: a.evidence, flags: a.review_flags ?? [], suggested_owner_name: a.suggested_owner_name,
    owner_resolution: a.owner_resolution, owner_candidates: a.owner_candidates ?? [], matches: a.existing_task_matches ?? [],
  })));
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  const stale = meeting.notes_changed_since_extraction;
  const setD = (i: number, patch: Partial<DecisionRow>) => setDecisions((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const setI = (i: number, patch: Partial<ItemRow>) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const used = items.filter((x) => x.action === "link" || x.action === "carry_forward").map((x) => x.existing_task_id);
  const problems = useMemo(() => {
    const p: string[] = [];
    items.forEach((x, i) => {
      if ((x.action === "link" || x.action === "carry_forward") && !x.existing_task_id) p.push(`Item ${i + 1}: choose an existing task`);
      if (x.action === "create" && x.title.trim().length < 3) p.push(`Item ${i + 1}: title required`);
    });
    if (new Set(used).size !== used.length) p.push("The same existing task is selected twice");
    if (summary.trim().length < 10) p.push("Summary is too short");
    return p;
  }, [items, used, summary]);

  const counts = {
    active: decisions.filter((d) => d.include && d.status === "active").length,
    proposed: decisions.filter((d) => d.include && d.status === "proposed").length,
    create: items.filter((x) => x.action === "create").length,
    carry: items.filter((x) => x.action === "carry_forward").length,
    link: items.filter((x) => x.action === "link").length,
    exclude: items.filter((x) => x.action === "exclude").length,
  };

  async function approve() {
    setBusy(true);
    try {
      await api(`/meetings/${meeting.id}/approve`, { body: {
        source_hash: draft.source_hash, approved_by: actorId, summary: summary.trim(),
        decisions: decisions.map((d) => ({ statement: d.statement.trim(), evidence: d.evidence, status: d.status, include: d.include })),
        action_items: items.map((x) => x.action === "exclude" ? { action: "exclude" } :
          x.action === "create" ? { action: "create", title: x.title.trim(), description: x.description || null, owner_id: x.owner_id,
            due_at: x.due_at || null, deadline_text: x.deadline_text || null, priority: x.priority, evidence: x.evidence }
          : { action: x.action, existing_task_id: x.existing_task_id, evidence: x.evidence }),
      } });
      toast.success("Approved. Official decisions and tasks were recorded in one transaction.");
      setConfirm(false);
      bump();
      onApproved();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  const ownerOptions = [...members].sort((a, b) => Number(participantIds.includes(b.id)) - Number(participantIds.includes(a.id)));

  return (
    <div className="flex flex-col gap-5">
      <Callout tone="indigo" icon={<CheckCircle2 className="w-4 h-4 text-indigo-600" />} title={`AI draft · ${draft.model}`}>
        Nothing below is official yet. Review, correct and approve. Quotes marked unverified could not be found in the original notes.
      </Callout>
      {stale && <Callout tone="rose" icon={<AlertTriangle className="w-4 h-4 text-rose-600" />} title="Notes changed after extraction">
        The original notes were edited after this draft was generated. Re-run extraction before approving.</Callout>}

      <Field label="Summary" htmlFor="rv-summary">
        <textarea id="rv-summary" rows={4} className={textareaCls} value={summary} onChange={(e) => setSummary(e.target.value)} />
      </Field>

      <div className="flex flex-col gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Decisions ({decisions.length})</h3>
        {decisions.length === 0 && <p className="text-xs text-slate-400">No decisions were extracted.</p>}
        {decisions.map((d, i) => (
          <div key={i} className={`rounded-lg border p-3 flex flex-col gap-2 ${d.include ? "border-surface-border bg-white" : "border-dashed border-slate-200 bg-slate-50 opacity-70"}`}>
            <div className="flex items-center gap-2 flex-wrap">
              <label className="flex items-center gap-1.5 text-xs font-medium text-slate-700">
                <input type="checkbox" checked={d.include} onChange={(e) => setD(i, { include: e.target.checked })} /> Include
              </label>
              <Badge tone={d.kind === "confirmed" ? "cyan" : "amber"}>AI: {d.kind}</Badge>
              <select aria-label="Record as" className={`${inputCls} !h-7 !w-auto`} value={d.status} onChange={(e) => setD(i, { status: e.target.value as any })}>
                <option value="active">Record as approved decision</option>
                <option value="proposed">Record as proposal only</option>
              </select>
              {!d.verified && <Badge tone="rose">quote unverified</Badge>}
            </div>
            <input aria-label="Decision statement" className={inputCls} value={d.statement} onChange={(e) => setD(i, { statement: e.target.value })} />
            <p className="text-[11px] text-slate-500 italic flex gap-1"><QuoteIcon className="w-3 h-3 shrink-0 mt-0.5" />{d.evidence}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Action items ({items.length})</h3>
        {items.length === 0 && <p className="text-xs text-slate-400">No action items were extracted.</p>}
        {items.map((x, i) => (
          <div key={i} className={`rounded-lg border p-3 flex flex-col gap-2.5 ${x.action === "exclude" ? "border-dashed border-slate-200 bg-slate-50 opacity-70" : "border-surface-border bg-white"}`}>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-[10px] text-slate-400">#{i + 1}</span>
              <select aria-label="Action" className={`${inputCls} !h-7 !w-auto`} value={x.action} onChange={(e) => setI(i, { action: e.target.value as any })}>
                <option value="create">Create new task</option>
                <option value="carry_forward">Carry forward existing task</option>
                <option value="link">Link to existing task</option>
                <option value="exclude">Exclude</option>
              </select>
              {x.flags.map((f) => <Badge key={f} tone="amber">{f.replace(/_/g, " ")}</Badge>)}
            </div>
            {x.action === "create" && (
              <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                <div className="md:col-span-5"><Field label="Title"><input className={inputCls} value={x.title} onChange={(e) => setI(i, { title: e.target.value })} /></Field></div>
                <div className="md:col-span-3">
                  <Field label="Owner" hint={x.suggested_owner_name ? `Notes: “${x.suggested_owner_name}” — ${RESOLUTION_TEXT[x.owner_resolution] ?? x.owner_resolution}` : RESOLUTION_TEXT.none}>
                    <select className={inputCls} value={x.owner_id ?? ""} onChange={(e) => setI(i, { owner_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">Unassigned</option>
                      {ownerOptions.map((m) => <option key={m.id} value={m.id}>{m.name}{participantIds.includes(m.id) ? "" : " (not in meeting)"}{x.owner_candidates.includes(m.id) ? " ★" : ""}</option>)}
                    </select>
                  </Field>
                </div>
                <div className="md:col-span-2"><Field label="Due date" hint={x.deadline_text ? `Notes: “${x.deadline_text}”` : "None stated"}>
                  <input type="date" className={inputCls} value={x.due_at} onChange={(e) => setI(i, { due_at: e.target.value })} /></Field></div>
                <div className="md:col-span-2"><Field label="Priority">
                  <select className={inputCls} value={x.priority} onChange={(e) => setI(i, { priority: e.target.value })}>
                    {["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}
                  </select></Field></div>
              </div>
            )}
            {(x.action === "link" || x.action === "carry_forward") && (
              <Field label="Existing task" hint={x.action === "carry_forward" ? "Keeps the same task ID, owner and status; adds this meeting to its history." : "Associates the task without changing it (completed tasks are not reopened)."}>
                <select className={inputCls} value={x.existing_task_id ?? ""} onChange={(e) => setI(i, { existing_task_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Choose a task…</option>
                  {x.matches.length > 0 && <optgroup label="Suggested matches">
                    {x.matches.map((mt) => <option key={`s${mt.task_id}`} value={mt.task_id}>TASK-{mt.task_id} · {mt.title} ({mt.status})</option>)}
                  </optgroup>}
                  <optgroup label="All project tasks">
                    {tasks?.map((t) => <option key={t.id} value={t.id}>TASK-{t.id} · {t.title} ({t.status}, {memberName(t.owner_id)})</option>)}
                  </optgroup>
                </select>
              </Field>
            )}
            {x.action !== "create" && x.action !== "exclude" && <p className="text-xs text-slate-600">AI item: <b>{x.title}</b></p>}
            <p className="text-[11px] text-slate-500 italic flex gap-1"><QuoteIcon className="w-3 h-3 shrink-0 mt-0.5" />{x.evidence}</p>
          </div>
        ))}
      </div>

      {problems.length > 0 && <Callout tone="amber" title="Resolve before approving">{problems.join(" · ")}</Callout>}
      <div className="flex justify-end">
        <Button variant="primary" disabled={stale || problems.length > 0} onClick={() => setConfirm(true)}>Approve extraction…</Button>
      </div>

      <ConfirmDialog open={confirm} loading={busy} onCancel={() => setConfirm(false)} onConfirm={approve} title="Approve meeting extraction"
        confirmLabel="Approve & record" message={<>
          As <b>{memberName(actorId)}</b> you will record:
          <ul className="list-disc pl-5 mt-2 space-y-0.5">
            <li>{counts.active} approved decision(s) and {counts.proposed} proposal(s)</li>
            <li>{counts.create} new task(s), {counts.carry} carried forward, {counts.link} linked, {counts.exclude} excluded</li>
          </ul>
          <p className="mt-2">This runs in one transaction and can only be approved once. <StatusBadge status="approved" /></p>
        </>} />
    </div>
  );
}

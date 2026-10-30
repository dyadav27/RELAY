import { useState } from "react";
import { Sparkles } from "lucide-react";
import { BriefSection } from "./RefChips";
import { Button, Callout, ErrorState, Field, Modal, inputCls } from "./ui";
import { useApp } from "../lib/context";
import { api } from "../lib/api";

function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

/** Re-entry brief for someone who missed meetings. Records are authoritative; AI only narrates. */
export function CatchUpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { project, members, actorId } = useApp();
  const [memberId, setMemberId] = useState<number | null>(null);
  const [since, setSince] = useState(daysAgo(7));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<unknown>(null);
  const who = memberId ?? actorId;

  async function run() {
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await api("/catch-up", { body: { project_id: project!.id, member_id: who, since } }));
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const b = result?.brief;
  return (
    <Modal open={open} onClose={onClose} wide title={<span className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-indigo-600" />Catch-up brief · {project?.name}</span>}>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
          <Field label="Team member" htmlFor="cu-member">
            <select id="cu-member" className={inputCls} value={who ?? ""} onChange={(e) => setMemberId(Number(e.target.value))}>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </Field>
          <Field label="Last participated" htmlFor="cu-since">
            <input id="cu-since" type="date" className={inputCls} value={since} max={daysAgo(0)} onChange={(e) => setSince(e.target.value)} />
          </Field>
          <Button variant="gradient" loading={busy} onClick={run} icon={<Sparkles className="w-4 h-4" />}>Generate brief</Button>
        </div>
        {!!error && <ErrorState error={error} />}
        {result && (
          <>
            <Callout tone={result.ai_status === "generated" ? "indigo" : "amber"}
              title={result.ai_status === "generated" ? "AI summary of RELAY records" : "Records-only brief (AI unavailable)"}>
              {result.ai_status === "generated"
                ? "Every line links to the database record it summarises. Check the linked records before acting."
                : result.ai_message}
            </Callout>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <BriefSection title="1 · What changed" items={b.what_changed} />
              <BriefSection title="2 · Decisions" items={b.decisions} />
              <BriefSection title="3 · Work completed" items={b.completed_work} />
              <BriefSection title="4 · Still outstanding" items={b.outstanding} />
              <BriefSection title="5 · Ownership changes" items={b.ownership_changes} />
              <BriefSection title="6 · Needs your attention" items={b.attention_next} />
            </div>
            <p className="text-[11px] text-slate-400">
              Based on {result.records.meetings.length} meeting(s), {result.records.decisions_approved.length} approved decision(s),
              {" "}{result.records.tasks_completed.length} completed and {result.records.tasks_created.length} new task(s) since {result.since}.
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Field, Modal, inputCls, textareaCls } from "./ui";
import { useApp } from "../lib/context";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import type { MeetingDetail } from "../lib/types";

function localNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function MeetingFormModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { project, projects, members, actorId, bump } = useApp();
  const toast = useToast();
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState<number>(project?.id ?? 0);
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState(localNow());
  const [agenda, setAgenda] = useState("");
  const [notes, setNotes] = useState("");
  const [participants, setParticipants] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) { setProjectId(project?.id ?? 0); setWhen(localNow()); }
  }, [open, project?.id]);

  const toggle = (id: number) => setParticipants((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const valid = title.trim().length >= 3 && notes.trim().length >= 20 && participants.length > 0;

  async function submit() {
    setSaving(true);
    try {
      const res = await api<MeetingDetail>("/meetings", { body: {
        project_id: projectId, title: title.trim(), meeting_at: new Date(when).toISOString(), agenda: agenda.trim() || null,
        raw_notes: notes.trim(), participant_ids: participants, created_by: actorId } });
      toast.success("Meeting saved. Original notes are preserved; run extraction when ready.");
      bump();
      setTitle(""); setAgenda(""); setNotes(""); setParticipants([]);
      onClose();
      navigate(`/meetings/${res.meeting.id}`);
    } catch (e) {
      toast.error(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Log meeting" wide
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={saving} disabled={!valid} onClick={submit}>Save meeting</Button></>}>
      <form className="grid grid-cols-1 md:grid-cols-2 gap-4" onSubmit={(e) => { e.preventDefault(); if (valid) submit(); }}>
        <Field label="Title" required htmlFor="mt-title">
          <input id="mt-title" className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Weekly Payment Integration Review" />
        </Field>
        <Field label="Date & time" required htmlFor="mt-when">
          <input id="mt-when" type="datetime-local" className={inputCls} value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
        <Field label="Project" required htmlFor="mt-project">
          <select id="mt-project" className={inputCls} value={projectId} onChange={(e) => setProjectId(Number(e.target.value))}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Participants" required hint="Owners suggested by AI are only matched against these people.">
          <div className="flex flex-wrap gap-1.5">
            {members.map((m) => (
              <button type="button" key={m.id} onClick={() => toggle(m.id)} aria-pressed={participants.includes(m.id)}
                className={`h-7 px-2.5 rounded-full border text-[11px] font-medium transition-colors ${participants.includes(m.id)
                  ? "bg-indigo-50 border-indigo-300 text-indigo-700" : "bg-white border-surface-border text-slate-600 hover:bg-slate-50"}`}>
                {m.name}
              </button>
            ))}
          </div>
        </Field>
        <div className="md:col-span-2">
          <Field label="Agenda" htmlFor="mt-agenda">
            <input id="mt-agenda" className={inputCls} value={agenda} onChange={(e) => setAgenda(e.target.value)} placeholder="Optional" />
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field label="Raw notes / transcript" required htmlFor="mt-notes" hint={`${notes.trim().length} characters (minimum 20). Stored verbatim; AI output is only a draft until approved.`}>
            <textarea id="mt-notes" rows={10} className={textareaCls} value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Paste meeting notes. Mention decisions, owners and deadlines explicitly where known." />
          </Field>
        </div>
      </form>
    </Modal>
  );
}

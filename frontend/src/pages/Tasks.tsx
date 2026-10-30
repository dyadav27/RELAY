import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { Badge, Button, Card, EmptyState, ErrorState, Field, LoadingState, Modal, PageHeader, StatusBadge, Table, inputCls, textareaCls } from "../components/ui";
import { useApp } from "../lib/context";
import { api, useApi } from "../lib/api";
import { useToast } from "../lib/toast";
import { fmtDate } from "../lib/format";
import type { Task, TaskDetail } from "../lib/types";

function NewTaskModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { project, members, actorId, bump } = useApp();
  const toast = useToast();
  const navigate = useNavigate();
  const [f, setF] = useState({ title: "", description: "", owner_id: "", due_at: "", priority: "medium", acceptance_criteria: "" });
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      const r = await api<TaskDetail>("/tasks", { body: { project_id: project!.id, title: f.title.trim(), description: f.description || null,
        owner_id: f.owner_id ? Number(f.owner_id) : null, due_at: f.due_at || null, priority: f.priority,
        acceptance_criteria: f.acceptance_criteria || null, actor_id: actorId } });
      toast.success("Task created."); bump(); onClose(); navigate(`/tasks/${r.task.id}`);
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }
  return (
    <Modal open={open} onClose={onClose} title="New task"
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={f.title.trim().length < 3} onClick={save}>Create task</Button></>}>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><Field label="Title" required><input className={inputCls} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field></div>
        <div className="col-span-2"><Field label="Description"><textarea rows={3} className={textareaCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
        <Field label="Owner"><select className={inputCls} value={f.owner_id} onChange={(e) => setF({ ...f, owner_id: e.target.value })}>
          <option value="">Unassigned</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
        <Field label="Due date"><input type="date" className={inputCls} value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} /></Field>
        <Field label="Priority"><select className={inputCls} value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
          {["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}</select></Field>
        <div className="col-span-2"><Field label="Acceptance criteria"><textarea rows={2} className={textareaCls} value={f.acceptance_criteria} onChange={(e) => setF({ ...f, acceptance_criteria: e.target.value })} /></Field></div>
      </div>
    </Modal>
  );
}

export function Tasks() {
  const { project, members, revision } = useApp();
  const [q, setQ] = useState("");
  const [owner, setOwner] = useState("");
  const [status, setStatus] = useState("open,in_progress,blocked");
  const [priority, setPriority] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [creating, setCreating] = useState(false);
  const qs = new URLSearchParams({ project_id: String(project!.id), r: String(revision) });
  if (q.trim()) qs.set("q", q.trim());
  if (owner) qs.set("owner_id", owner);
  if (status) qs.set("status", status);
  if (priority) qs.set("priority", priority);
  if (overdue) qs.set("overdue", "true");
  const { data, error, loading, reload } = useApi<Task[]>(`/tasks?${qs}`);

  return (
    <>
      <PageHeader title="Work Continuity" description="Tasks keep one identity across meetings; every change is recorded in history."
        actions={<Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => setCreating(true)}>New task</Button>} />
      <Card padded={false}>
        <div className="p-4 flex flex-wrap gap-2 items-center border-b border-surface-border">
          <div className="relative flex-1 min-w-[12rem]">
            <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-2.5" />
            <input aria-label="Search tasks" className={`${inputCls} pl-8`} placeholder="Search tasks…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select aria-label="Owner filter" className={`${inputCls} !w-auto`} value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">All owners</option><option value="0">Unassigned</option>{members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <select aria-label="Status filter" className={`${inputCls} !w-auto`} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open,in_progress,blocked">Unfinished</option><option value="">All statuses</option>
            {["open", "in_progress", "blocked", "completed", "cancelled"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </select>
          <select aria-label="Priority filter" className={`${inputCls} !w-auto`} value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All priorities</option>{["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-700 px-2"><input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />Overdue only</label>
        </div>
        {loading && !data ? <LoadingState /> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : (
          <Table head={["Task", "Owner", "Status", "Priority", "Due", "Updated"]}
            empty={data?.length === 0 ? <EmptyState title="No tasks match these filters" /> : null}>
            {data?.map((t) => (
              <tr key={t.id} className="hover:bg-slate-50/50">
                <td className="py-3 px-5">
                  <Link to={`/tasks/${t.id}`} className="font-semibold text-slate-900 hover:text-indigo-700">{t.title}</Link>
                  <p className="font-mono text-[10px] text-slate-400">TASK-{t.id}</p>
                </td>
                <td className="py-3 px-4 text-slate-700">{t.owner_name ?? <Badge tone="amber">Unassigned</Badge>}</td>
                <td className="py-3 px-4"><StatusBadge status={t.status} /></td>
                <td className="py-3 px-4"><StatusBadge status={t.priority} /></td>
                <td className="py-3 px-4 whitespace-nowrap">
                  {t.due_at ? <span className={t.is_overdue ? "text-rose-600 font-semibold" : "text-slate-600"}>{fmtDate(t.due_at)}</span>
                    : <span className="text-slate-400">{t.deadline_text ? `“${t.deadline_text}”` : "No deadline"}</span>}
                  {t.is_overdue && <Badge tone="rose" className="ml-1.5">Overdue</Badge>}
                </td>
                <td className="py-3 px-4 text-slate-500 whitespace-nowrap">{fmtDate(t.updated_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <NewTaskModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FileText, GitBranch, MessageCircleQuestion, Search, Upload, ShieldQuestion } from "lucide-react";
import { RefChip } from "../components/RefChips";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, Field, LoadingState, Modal, PageHeader, StatusBadge, Table, inputCls } from "../components/ui";
import { useApp } from "../lib/context";
import { api, useApi } from "../lib/api";
import { useToast } from "../lib/toast";
import { fmtDate, refRoute } from "../lib/format";
import type { Decision } from "../lib/types";

const TABS = { ask: "Ask with evidence", search: "Search", documents: "Documents", decisions: "Decision ledger" } as const;

const ANSWER_TONE = { supported: "cyan", conflicting: "amber", insufficient_evidence: "slate" } as const;

function Ask() {
  const { project, actorId } = useApp();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<unknown>(null);
  const examples = ["Which authentication approach is approved for the payment API?", "What is blocking the authentication workflow review?",
    "What is the approved migration budget?", "How are webhook payloads verified?"];

  async function ask(question = q) {
    if (question.trim().length < 3) return;
    setQ(question); setBusy(true); setError(null); setRes(null);
    try { setRes(await api("/knowledge/ask", { body: { project_id: project!.id, question: question.trim(), actor_id: actorId } })); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <form className="flex flex-col sm:flex-row gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <input aria-label="Question" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask about ${project!.name} decisions, tasks, meetings or documents…`} />
          <Button type="submit" variant="primary" loading={busy} disabled={q.trim().length < 3} icon={<MessageCircleQuestion className="w-4 h-4" />}>Ask</Button>
        </form>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {examples.map((x) => <button key={x} onClick={() => ask(x)} className="text-[11px] px-2.5 py-1 rounded-full border border-surface-border text-slate-600 hover:bg-slate-50">{x}</button>)}
        </div>
        <p className="text-[11px] text-slate-400 mt-3">Answers use only records from this project. Uploaded documents are treated as untrusted text.</p>
      </Card>
      {!!error && <ErrorState error={error} />}
      {res && (
        <Card title={<div className="flex items-center gap-2"><h3 className="text-sm font-bold text-slate-900">Answer</h3>
          <Badge tone={ANSWER_TONE[res.status as keyof typeof ANSWER_TONE]} dot>{res.status.replace(/_/g, " ")}</Badge></div>}
          subtitle={`${res.retrieved_count} records retrieved · run #${res.answer_run_id}`}>
          <div className="flex flex-col gap-4">
            {res.status === "insufficient_evidence" ? (
              <Callout tone="slate" icon={<ShieldQuestion className="w-4 h-4 text-slate-500" />} title="Not enough evidence">
                {res.answer}{res.missing_information ? <span className="block mt-1 text-slate-500">Missing: {res.missing_information}</span> : null}
              </Callout>
            ) : <p className="text-sm text-slate-800 leading-relaxed">{res.answer}</p>}
            {res.claims.length > 0 && (
              <div className="flex flex-col gap-2">
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Claims and their sources</h4>
                {res.claims.map((c: any, i: number) => (
                  <div key={i} className="flex flex-wrap items-start gap-2 text-xs p-2.5 rounded-md bg-slate-50 border border-surface-border">
                    <span className="flex-1 min-w-[12rem] text-slate-800">{c.text}</span>
                    <span className="flex flex-wrap gap-1">{c.source_ids.map((s: string) => <a key={s} href={`#src-${s}`}><RefChip id={s} /></a>)}</span>
                  </div>
                ))}
              </div>
            )}
            {res.conflicts.length > 0 && (
              <Callout tone="amber" title="Conflicting records">
                <ul className="flex flex-col gap-1.5 mt-1">{res.conflicts.map((c: any, i: number) => (
                  <li key={i} className="flex flex-wrap gap-1.5 items-center">{c.description}{c.source_ids.map((s: string) => <RefChip key={s} id={s} />)}</li>))}</ul>
                <p className="mt-1.5 text-slate-500">RELAY does not pick the most recent discussion as the decision; check approval status below.</p>
              </Callout>
            )}
            {res.rejected_claims.length > 0 && (
              <Callout tone="rose" title={`${res.rejected_claims.length} claim(s) removed`}>The model cited record IDs that were not retrieved, or claimed an approval its sources do not record (discussion is not approval), so those claims are not shown.</Callout>
            )}
            {res.sources.length > 0 && (
              <div className="flex flex-col gap-2">
                <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Cited records</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {res.sources.map((s: any) => {
                    const route = s.type === "document_chunk" ? `/knowledge?tab=documents&document=${s.document_id}` : refRoute(s.id);
                    return (
                      <div key={s.id} id={`src-${s.id}`} className="p-3 rounded-lg border border-surface-border bg-white text-xs flex flex-col gap-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <RefChip id={s.id} />
                          {route ? <Link to={route} className="font-semibold text-slate-800 hover:text-indigo-700">{s.label}</Link> : <span className="font-semibold">{s.label}</span>}
                          {s.status && <StatusBadge status={s.status} />}
                        </div>
                        <p className="text-slate-600 line-clamp-4">{s.text}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            <p className="text-[11px] text-slate-400">A valid reference shows which RELAY record a claim cites; it does not guarantee the AI interpreted it correctly. Open the source to verify.</p>
          </div>
        </Card>
      )}
    </div>
  );
}

function SearchTab() {
  const { project } = useApp();
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, loading, error } = useApi<any>(submitted ? `/knowledge/search?project_id=${project!.id}&q=${encodeURIComponent(submitted)}` : null);
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setSubmitted(q.trim()); }}>
          <input aria-label="Search query" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Full-text search across documents, meetings, decisions and tasks" />
          <Button type="submit" variant="primary" disabled={q.trim().length < 2} icon={<Search className="w-4 h-4" />}>Search</Button>
        </form>
      </Card>
      {loading && <LoadingState />}{!!error && <ErrorState error={error} />}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card title={`Document passages (${data.chunks.length})`}>
            {data.chunks.length === 0 ? <p className="text-xs text-slate-400">No matches.</p> : data.chunks.map((c: any) => (
              <div key={c.id} className="py-2 border-b border-surface-border last:border-0 text-xs">
                <Link to={`/knowledge?tab=documents&document=${c.document_id}`} className="font-semibold text-slate-800 hover:text-indigo-700">{c.document_title} v{c.version_number}</Link>
                <span className="text-slate-400 font-mono text-[10px] ml-2">chunk {c.chunk_index}{c.page_number ? ` · p.${c.page_number}` : ""}</span>
                <p className="text-slate-600 mt-1">{c.excerpt}</p>
              </div>))}
          </Card>
          <Card title={`Meetings (${data.meetings.length})`}>
            {data.meetings.length === 0 ? <p className="text-xs text-slate-400">No matches.</p> : data.meetings.map((m: any) => (
              <div key={m.id} className="py-2 border-b border-surface-border last:border-0 text-xs">
                <Link to={`/meetings/${m.id}`} className="font-semibold text-slate-800 hover:text-indigo-700">{m.title}</Link>
                <p className="text-slate-600 mt-1 whitespace-pre-wrap">{m.excerpt}</p>
              </div>))}
          </Card>
          <Card title={`Decisions (${data.decisions.length})`}>
            {data.decisions.length === 0 ? <p className="text-xs text-slate-400">No matches.</p> : data.decisions.map((d: Decision) => (
              <div key={d.id} className="py-2 border-b border-surface-border last:border-0 text-xs flex gap-2 items-start">
                <span className="font-mono font-bold text-indigo-600">{d.code}</span><span className="flex-1 text-slate-700">{d.statement}</span><StatusBadge status={d.status} />
              </div>))}
          </Card>
          <Card title={`Tasks (${data.tasks.length})`}>
            {data.tasks.length === 0 ? <p className="text-xs text-slate-400">No matches.</p> : data.tasks.map((t: any) => (
              <div key={t.id} className="py-2 border-b border-surface-border last:border-0 text-xs flex gap-2 items-center">
                <Link to={`/tasks/${t.id}`} className="flex-1 font-medium text-slate-800 hover:text-indigo-700">{t.title}</Link><StatusBadge status={t.status} />
              </div>))}
          </Card>
        </div>
      )}
    </div>
  );
}

function Documents({ focus }: { focus: number | null }) {
  const { project, actorId, bump } = useApp();
  const toast = useToast();
  const { data, loading, error, reload } = useApi<any[]>(`/knowledge/documents?project_id=${project!.id}`);
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<number | null>(focus);
  const { data: doc } = useApi<any>(viewing ? `/knowledge/documents/${viewing}` : null);
  useEffect(() => setViewing(focus), [focus]);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("project_id", String(project!.id));
    form.append("file", file);
    if (title.trim()) form.append("title", title.trim());
    if (actorId) form.append("uploaded_by", String(actorId));
    setBusy(true);
    try {
      const d = await api<any>("/knowledge/documents", { form });
      toast.success(`Indexed “${d.title}” v${d.version_number}.`);
      setTitle(""); if (fileRef.current) fileRef.current.value = "";
      bump(); reload();
    } catch (e) { toast.error(e); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-5">
      <Card title="Upload document" subtitle="PDF (text-based), TXT or Markdown · max 5 MB">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3 items-end">
          <Field label="File" htmlFor="doc-file"><input id="doc-file" ref={fileRef} type="file" accept=".pdf,.txt,.md,.markdown" className="text-xs file:mr-3 file:h-8 file:px-3 file:rounded-md file:border file:border-surface-border file:bg-white file:text-xs file:font-semibold" /></Field>
          <Field label="Title" hint="Same title as an existing document creates a new version." htmlFor="doc-title"><input id="doc-title" className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Defaults to file name" /></Field>
          <Button variant="primary" loading={busy} onClick={upload} icon={<Upload className="w-4 h-4" />}>Upload & index</Button>
        </div>
        <p className="text-[11px] text-slate-500 mt-3">Scanned PDFs without a text layer are rejected (no OCR). Uploads are not approvals: a document is evidence, not a decision.</p>
      </Card>
      <Card padded={false} title="Project documents">
        {loading && !data ? <LoadingState /> : error ? <div className="p-5"><ErrorState error={error} /></div> : (
          <Table head={["Title", "Version", "Status", "File", "Indexed", "Uploaded"]} empty={data?.length === 0 ? <EmptyState title="No documents yet" /> : null}>
            {data?.map((d) => (
              <tr key={d.id} className="hover:bg-slate-50/50">
                <td className="py-3 px-5"><button onClick={() => setViewing(d.id)} className="font-semibold text-slate-900 hover:text-indigo-700 flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-slate-400" />{d.title}</button></td>
                <td className="py-3 px-4 font-mono">v{d.version_number}</td>
                <td className="py-3 px-4"><StatusBadge status={d.document_status} /> <Badge tone="slate">unreviewed</Badge></td>
                <td className="py-3 px-4 text-slate-500">{d.source_filename}</td>
                <td className="py-3 px-4 text-slate-500">{d.chunk_count} chunks</td>
                <td className="py-3 px-4 text-slate-500 whitespace-nowrap">{fmtDate(d.created_at)}{d.uploaded_by_name ? ` · ${d.uploaded_by_name}` : ""}</td>
              </tr>))}
          </Table>)}
      </Card>
      <Modal open={!!viewing && !!doc} onClose={() => setViewing(null)} wide title={doc ? `${doc.title} v${doc.version_number}` : ""}>
        {doc && <><p className="text-[11px] text-slate-500 mb-3">{doc.source_filename} · {doc.chunk_count} chunks · {doc.document_status}</p>
          <pre className="text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{doc.content_text}</pre></>}
      </Modal>
    </div>
  );
}

function Ledger({ focus }: { focus: number | null }) {
  const { project, revision } = useApp();
  const [status, setStatus] = useState("");
  const { data, loading, error } = useApi<Decision[]>(`/decisions?project_id=${project!.id}${status ? `&status=${status}` : ""}&r=${revision}`);
  useEffect(() => { if (focus && data) document.getElementById(`dec-${focus}`)?.scrollIntoView({ block: "center" }); }, [focus, data]);
  const code = (id: number) => `DEC-${String(id).padStart(4, "0")}`;
  return (
    <Card title="Decision ledger" subtitle="Approved decisions, proposals and supersession lineage"
      actions={<select aria-label="Decision status" className={`${inputCls} !h-8 !w-auto`} value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All statuses</option>{["active", "proposed", "superseded", "rejected"].map((s) => <option key={s}>{s}</option>)}</select>}>
      {loading && !data ? <LoadingState /> : error ? <ErrorState error={error} /> : data?.length === 0 ? <EmptyState title="No decisions" /> : (
        <div className="flex flex-col gap-3">
          {data?.map((d) => (
            <div key={d.id} id={`dec-${d.id}`} className={`p-4 rounded-lg border flex flex-col gap-2 ${focus === d.id ? "border-indigo-400 ring-2 ring-indigo-100" : "border-surface-border"} ${d.status === "superseded" ? "bg-slate-50" : "bg-white"}`}>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-bold text-indigo-600">{d.code}</span><StatusBadge status={d.status} />
                {d.meeting_title && <Link to={`/meetings/${d.meeting_id}`} className="text-[11px] px-2 py-0.5 rounded-md border border-slate-200 text-slate-600 hover:text-indigo-700">{d.meeting_title}</Link>}
              </div>
              <p className={`text-xs font-semibold ${d.status === "superseded" ? "text-slate-500 line-through decoration-slate-300" : "text-slate-900"}`}>{d.statement}</p>
              {d.evidence && <p className="text-[11px] text-slate-500 italic">Evidence: “{d.evidence}”</p>}
              <p className="text-[11px] text-slate-500">
                {d.approved_at ? <>Approved by <b>{d.approved_by_name}</b> on {fmtDate(d.approved_at)}</> : "Not approved (proposal)"}
                {d.effective_until && <> · effective until {fmtDate(d.effective_until)}</>}
              </p>
              {d.lineage && (d.lineage.supersedes.length + d.lineage.superseded_by.length + d.lineage.proposed_changes.length + d.lineage.proposes_change_to.length > 0) && (
                <div className="flex flex-wrap gap-2 text-[11px] text-slate-600 items-center">
                  <GitBranch className="w-3.5 h-3.5 text-indigo-500" />
                  {d.lineage.supersedes.map((r) => <span key={`s${r.decision_id}`}>Supersedes <a className="font-mono text-indigo-700" href={`#dec-${r.decision_id}`}>{code(r.decision_id)}</a></span>)}
                  {d.lineage.superseded_by.map((r) => <span key={`b${r.decision_id}`}>Superseded by <a className="font-mono text-indigo-700" href={`#dec-${r.decision_id}`}>{code(r.decision_id)}</a>{r.reason ? ` — ${r.reason}` : ""}</span>)}
                  {d.lineage.proposes_change_to.map((r) => <span key={`p${r.decision_id}`}>Proposes change to <a className="font-mono text-indigo-700" href={`#dec-${r.decision_id}`}>{code(r.decision_id)}</a></span>)}
                  {d.lineage.proposed_changes.map((r) => <span key={`c${r.decision_id}`}>Change proposed in <a className="font-mono text-indigo-700" href={`#dec-${r.decision_id}`}>{code(r.decision_id)}</a></span>)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function Knowledge() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") ?? "ask") as keyof typeof TABS;
  const focusDoc = params.get("document") ? Number(params.get("document")) : null;
  const focusDec = params.get("decision") ? Number(params.get("decision")) : null;
  return (
    <>
      <PageHeader title="Knowledge Hub" description="Proof-carrying answers, full-text search, project documents and the decision ledger." />
      <div className="flex gap-1 border-b border-surface-border overflow-x-auto" role="tablist">
        {(Object.keys(TABS) as (keyof typeof TABS)[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setParams({ tab: t })}
            className={`px-3 py-2 text-xs font-semibold whitespace-nowrap border-b-2 -mb-px ${tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>{TABS[t]}</button>
        ))}
      </div>
      {tab === "ask" && <Ask />}
      {tab === "search" && <SearchTab />}
      {tab === "documents" && <Documents focus={focusDoc} />}
      {tab === "decisions" && <Ledger focus={focusDec} />}
    </>
  );
}

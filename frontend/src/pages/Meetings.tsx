import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useUiActions } from "../components/Layout";
import { Button, Card, EmptyState, ErrorState, IntegrityBadge, LoadingState, PageHeader, StatusBadge, Table } from "../components/ui";
import { useApp } from "../lib/context";
import { useApi } from "../lib/api";
import { fmtDate } from "../lib/format";
import type { Meeting } from "../lib/types";

export function Meetings() {
  const { project, revision } = useApp();
  const { openLogMeeting } = useUiActions();
  const { data, error, loading, reload } = useApi<Meeting[]>(`/meetings?project_id=${project!.id}&r=${revision}`);

  return (
    <>
      <PageHeader title="Meeting Intelligence" description={<>Notes are stored verbatim. AI extraction is a draft until a person approves it. Project: <b className="text-slate-700">{project!.name}</b></>}
        actions={<Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={openLogMeeting}>Log meeting</Button>} />
      <Card padded={false}>
        {loading && !data ? <LoadingState /> : error ? <div className="p-5"><ErrorState error={error} onRetry={reload} /></div> : (
          <Table head={["Meeting", "Date", "Participants", "Summary", "Extraction", "Decision integrity"]}
            empty={data?.length === 0 ? <EmptyState title="No meetings logged" description="Log meeting notes to extract decisions and tasks." action={<Button size="sm" onClick={openLogMeeting}>Log meeting</Button>} /> : null}>
            {data?.map((m) => (
              <tr key={m.id} className="hover:bg-slate-50/50">
                <td className="py-3.5 px-5"><Link to={`/meetings/${m.id}`} className="font-semibold text-slate-900 hover:text-indigo-700">{m.title}</Link></td>
                <td className="py-3.5 px-4 whitespace-nowrap text-slate-600">{fmtDate(m.meeting_at, true)}</td>
                <td className="py-3.5 px-4 text-slate-600">
                  {m.participants.map((p) => <span key={p.member_id} className={p.attendance_status === "absent" ? "line-through text-slate-400 mr-1" : "mr-1"}>{p.name}</span>)}
                </td>
                <td className="py-3.5 px-4 text-slate-600 max-w-sm"><span className="line-clamp-2">{m.summary_preview ?? <span className="text-slate-400">No summary yet</span>}</span></td>
                <td className="py-3.5 px-4"><StatusBadge status={m.extraction_status} /></td>
                <td className="py-3.5 px-4"><IntegrityBadge integrity={m.integrity} /></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}

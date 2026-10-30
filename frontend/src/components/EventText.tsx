import { Link } from "react-router-dom";
import type { TaskEvent } from "../lib/types";
import { label } from "../lib/format";
import { TimelineItem } from "./ui";
import { relTime } from "../lib/format";

/** Human-readable rendering of a task_events row. */
export function EventText({ e, showTask = false }: { e: TaskEvent; showTask?: boolean }) {
  const task = showTask && e.task_title
    ? <Link to={`/tasks/${e.task_id}`} className="font-semibold text-slate-800 hover:text-indigo-700">{e.task_title}</Link>
    : null;
  const t = task ? <> {task}</> : null;
  let body: React.ReactNode;
  switch (e.event_type) {
    case "created": body = <>Created{t}</>; break;
    case "reassigned":
      body = <>Reassigned{t} from <b className="font-semibold text-slate-800">{e.old_value?.owner_name ?? "unassigned"}</b> to{" "}
        <b className="font-semibold text-indigo-700">{e.new_value?.owner_name ?? "unassigned"}</b></>;
      break;
    case "status_changed":
      body = <>Moved{t} from {label(e.old_value?.status ?? "?")} to <b className="font-semibold text-slate-800">{label(e.new_value?.status ?? "?")}</b></>;
      break;
    case "carry_forward":
      body = <>Carried forward{t} to <Link className="text-indigo-700 font-medium hover:underline" to={`/meetings/${e.meeting_id}`}>{e.new_value?.meeting_title ?? "meeting"}</Link></>;
      break;
    case "linked_to_meeting":
      body = <>Linked{t} to <Link className="text-indigo-700 font-medium hover:underline" to={`/meetings/${e.meeting_id}`}>{e.new_value?.meeting_title ?? "meeting"}</Link></>;
      break;
    case "completed": body = <>Completed{t}{e.new_value?.outcome ? <>: <i>{e.new_value.outcome}</i></> : null}</>; break;
    case "cancelled": body = <>Cancelled{t}{e.new_value?.outcome ? <>: <i>{e.new_value.outcome}</i></> : null}</>; break;
    case "reopened": body = <>Reopened{t}</>; break;
    case "deadline_changed": body = <>Changed deadline{t} to {e.new_value?.due_at ? new Date(e.new_value.due_at).toLocaleDateString() : "none"}</>; break;
    case "blocker_recorded": body = <>Recorded a blocker{t}</>; break;
    case "decision_review": body = <>Flagged{t} for review after a decision change</>; break;
    case "updated": body = <>Updated {Object.keys(e.new_value ?? {}).map(label).join(", ")}{t}</>; break;
    case "comment": body = <>Commented{t}</>; break;
    default: body = <>{label(e.event_type)}{t}</>;
  }
  return <>{body}{e.note && <span className="block text-slate-500 mt-0.5">“{e.note}”</span>}</>;
}

const TONE: Record<string, "cyan" | "indigo" | "slate" | "amber" | "rose"> = {
  completed: "cyan", carry_forward: "indigo", reassigned: "indigo", status_changed: "slate", decision_review: "amber",
  blocker_recorded: "rose", reopened: "amber", created: "slate",
};

export function EventTimelineItem({ e, showTask }: { e: TaskEvent; showTask?: boolean }) {
  const tone = e.event_type === "status_changed" && e.new_value?.status === "blocked" ? "rose" : TONE[e.event_type] ?? "slate";
  return (
    <TimelineItem who={e.actor_name} when={relTime(e.created_at)} tone={tone}>
      <EventText e={e} showTask={showTask} />
    </TimelineItem>
  );
}

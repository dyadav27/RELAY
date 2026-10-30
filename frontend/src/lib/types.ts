export type Project = { id: number; name: string; description: string | null; workspace_id: number; workspace_name: string; is_demo_data: boolean };
export type Member = { id: number; name: string; email: string; role: string; is_active: boolean };

export type TaskStatus = "open" | "in_progress" | "blocked" | "completed" | "cancelled";
export type Task = {
  id: number; project_id: number; title: string; description: string | null; owner_id: number | null;
  owner_name: string | null; origin_meeting_id: number | null; due_at: string | null; deadline_text: string | null;
  acceptance_criteria: string | null; status: TaskStatus; priority: "low" | "medium" | "high" | "critical";
  outcome: string | null; version: number; is_overdue: boolean; created_at: string; updated_at: string;
  completed_at: string | null; relationship_type?: string;
};
export type TaskEvent = {
  id: number; task_id: number; event_type: string; actor_id: number | null; actor_name: string; old_value: any;
  new_value: any; note: string | null; meeting_id: number | null; created_at: string; task_title?: string | null;
};

export type Decision = {
  id: number; code: string; project_id: number; meeting_id: number | null; meeting_title: string | null;
  statement: string; evidence: string | null; status: "proposed" | "active" | "superseded" | "rejected";
  approved_by: number | null; approved_by_name: string | null; approved_at: string | null;
  effective_from: string | null; effective_until: string | null; created_at: string;
  lineage?: { supersedes: Rel[]; superseded_by: Rel[]; proposed_changes: Rel[]; proposes_change_to: Rel[] };
};
type Rel = { decision_id: number; reason: string | null; created_at: string };

export type Alert = {
  id: number; code: string; meeting: { id: number; title: string; meeting_at: string }; existing_decision: Decision;
  proposed_statement: string; classification: string; explanation: string; old_evidence: string | null;
  new_evidence: string | null; affected_tasks: { id: number; title: string; status: TaskStatus; owner_name: string | null }[];
  status: string; resolved_by_name: string | null; resolved_at: string | null; resolution_note: string | null; created_at: string;
};

export type Meeting = {
  id: number; project_id: number; title: string; record_type: string; meeting_at: string; agenda: string | null;
  summary: string | null; summary_preview: string | null; extraction_status: "pending" | "extracted" | "approved" | "failed";
  notes_changed_since_extraction: boolean; source_hash: string;
  participants: { member_id: number; name: string; attendance_status: string }[];
  integrity: { state: string; pending_alerts: number; resolved_alerts: number };
  raw_notes?: string; extraction_draft?: any; key_decision?: { code: string; statement: string; status: string } | null;
};

export type MeetingDetail = {
  meeting: Meeting; project: { id: number; name: string }; tasks: Task[]; decisions: Decision[]; alerts: Alert[];
  related_documents: { id: number; title: string; version_number: number }[]; activity: TaskEvent[];
};

export type TaskDetail = {
  task: Task; project: { id: number; name: string };
  meetings: { id: number; title: string; meeting_at: string; relationship_type: string; linked_at: string }[];
  decisions: Decision[]; decision_alerts: Alert[]; events: TaskEvent[];
};

export type Handover = {
  id: number; project_id: number; project_name: string; status: "draft" | "approved" | "cancelled";
  from_member: { id: number; name: string }; to_member: { id: number; name: string }; start_date: string;
  end_date: string | null; created_at: string; approved_at: string | null; approved_by_name: string | null;
  brief_text: string | null; brief_json: any; transferred_task_ids?: number[];
  tasks: { task: Task; selected: boolean; transferred_at: string | null }[];
};

export type Dashboard = {
  project: { id: number; name: string; description: string | null }; workspace: { id: number; name: string };
  is_demo_data: boolean; generated_at: string;
  metrics: { open_tasks: number; in_progress: number; blocked: number; unassigned: number; overdue: number;
    completed_last_7d: number; completed_total: number; pending_decision_alerts: number; meetings: number };
  pending_alerts: Alert[]; recent_meetings: Meeting[]; recent_decisions: Decision[]; latest_handover: Handover | null;
  activity: TaskEvent[];
};

export type BriefItem = { text: string; refs: string[] };

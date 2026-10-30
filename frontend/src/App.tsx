import { Link, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { EmptyState } from "./components/ui";
import { Overview } from "./pages/Overview";
import { Meetings } from "./pages/Meetings";
import { MeetingDetail } from "./pages/MeetingDetail";
import { Tasks } from "./pages/Tasks";
import { TaskDetail } from "./pages/TaskDetail";
import { Knowledge } from "./pages/Knowledge";
import { Handover } from "./pages/Handover";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/meetings" element={<Meetings />} />
        <Route path="/meetings/:id" element={<MeetingDetail />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/tasks/:id" element={<TaskDetail />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/handover" element={<Handover />} />
        <Route path="*" element={<EmptyState title="Page not found" action={<Link className="text-xs text-indigo-700 underline" to="/overview">Back to overview</Link>} />} />
      </Route>
    </Routes>
  );
}

import { NavLink } from "react-router-dom";
import { BookOpen, CheckCircle2, LayoutDashboard, Sparkles, Video, LayoutGrid, FileCode2 } from "lucide-react";
import { useApp } from "../lib/context";
import { useApi } from "../lib/api";
import type { Dashboard } from "../lib/types";

export function RelayLogo() {
  return (
    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-purple-600 to-cyan-400 p-[1.5px] shadow-sm shadow-indigo-500/20">
      <div className="w-full h-full bg-sidebar rounded-[6.5px] flex items-center justify-center">
        <svg className="w-5 h-5" fill="none" viewBox="0 0 40 40" aria-hidden>
          <path d="M12 32V8H22C26.5 8 29.5 11 29.5 15.5C29.5 19 27.2 21.8 24 22.6L31 32H24.5L18.2 23.5H16.8V32H12ZM16.8 19H21.5C23.8 19 25 17.6 25 15.5C25 13.4 23.8 12 21.5 12H16.8V19Z" fill="url(#relay_grad)" />
          <defs>
            <linearGradient gradientUnits="userSpaceOnUse" id="relay_grad" x1="12" x2="31" y1="8" y2="32">
              <stop stopColor="#818CF8" /><stop offset="0.5" stopColor="#6366F1" /><stop offset="1" stopColor="#06B6D4" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  );
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { project, projects, setProjectId, revision } = useApp();
  const { data } = useApi<Dashboard>(project ? `/dashboard?project_id=${project.id}&r=${revision}` : null);
  const m = data?.metrics;
  const nav = [
    { to: "/overview", label: "Overview", icon: LayoutDashboard },
    { to: "/meetings", label: "Meetings", icon: Video, count: m?.meetings },
    { to: "/tasks", label: "Tasks", icon: CheckCircle2, count: m?.open_tasks },
    { to: "/knowledge", label: "Knowledge Hub", icon: BookOpen },
    { to: "/handover", label: "Handover Copilot", icon: Sparkles, ai: true },
  ];

  return (
    <>
      {open && <div className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden" onClick={onClose} />}
      <aside className={`fixed left-0 top-0 bottom-0 w-64 bg-sidebar text-slate-200 flex flex-col z-50 border-r border-slate-800/80 shadow-xl transition-transform lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="px-5 pt-5 pb-4 flex items-center justify-between border-b border-slate-800/60">
          <div className="flex items-center gap-2.5">
            <RelayLogo />
            <span className="font-bold text-lg tracking-wider text-white">RELAY</span>
          </div>
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/10 text-cyan-300 border border-cyan-500/20 tracking-wider">MVP</span>
        </div>

        <div className="px-4 py-3">
          <label className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-300 transition-colors border border-slate-800 cursor-pointer">
            <div className="w-6 h-6 rounded bg-indigo-500/10 flex items-center justify-center text-cyan-400 shrink-0">
              <LayoutGrid className="w-4 h-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 leading-none">
                {project?.workspace_name ?? "Workspace"}
              </p>
              <select aria-label="Project" value={project?.id ?? ""} onChange={(e) => setProjectId(Number(e.target.value))}
                className="w-full bg-transparent text-xs font-medium text-white truncate mt-0.5 focus:outline-none cursor-pointer appearance-none">
                {projects.map((p) => <option key={p.id} value={p.id} className="text-slate-900">{p.name}</option>)}
              </select>
            </div>
          </label>
        </div>

        <div className="px-5 pt-3 pb-1.5"><p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Operations</p></div>
        <nav className="flex-1 px-3 flex flex-col gap-1">
          {nav.map(({ to, label, icon: Icon, count, ai }) => (
            <NavLink key={to} to={to} onClick={onClose}
              className={({ isActive }) => `group flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${isActive
                ? "text-white font-semibold bg-gradient-to-r from-indigo-600/30 to-cyan-500/10 border border-indigo-500/30 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 font-medium border border-transparent"}`}>
              {({ isActive }) => (
                <>
                  <div className="flex items-center gap-3">
                    <Icon className={`w-[18px] h-[18px] ${isActive ? "text-cyan-400" : "text-slate-400 group-hover:text-indigo-400"}`} />
                    <span>{label}</span>
                  </div>
                  {isActive ? <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-sm shadow-cyan-400" />
                    : ai ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gradient-to-r from-indigo-500 to-cyan-500 text-white tracking-wide">AI</span>
                    : count !== undefined ? <span className="font-mono text-[11px] px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 border border-slate-700/50">{count}</span>
                    : null}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800/70 flex flex-col gap-3 bg-slate-950/40">
          <div className="p-3 rounded-lg bg-slate-900 border border-slate-800/90 flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Integrity queue</span>
              <span className={`w-2 h-2 rounded-full ${m?.pending_decision_alerts ? "bg-amber-400" : "bg-cyan-400"}`} />
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-slate-300">Decisions to review</span>
              <span className="font-mono text-xs font-bold text-cyan-400">{m?.pending_decision_alerts ?? "–"}</span>
            </div>
          </div>
          <a href="/docs" target="_blank" rel="noreferrer"
            className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-colors">
            <FileCode2 className="w-4 h-4" /> API documentation
          </a>
        </div>
      </aside>
    </>
  );
}

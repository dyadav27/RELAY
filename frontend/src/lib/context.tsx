import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import type { Member, Project } from "./types";

type Ctx = {
  projects: Project[];
  project: Project | null;
  setProjectId: (id: number) => void;
  members: Member[];
  memberName: (id: number | null | undefined) => string;
  actorId: number | null;
  setActorId: (id: number) => void;
  /** Incremented after mutations so dependent views (sidebar counts, dashboard) reload. */
  revision: number;
  bump: () => void;
  bootError: ApiError | null;
  ready: boolean;
};

const AppContext = createContext<Ctx | null>(null);

function stored(key: string): number | null {
  try {
    const v = localStorage.getItem(key);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}
function store(key: string, v: number) {
  try {
    localStorage.setItem(key, String(v));
  } catch {
    /* storage unavailable: keep in memory only */
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectIdState] = useState<number | null>(stored("relay.project"));
  const [members, setMembers] = useState<Member[]>([]);
  const [actorId, setActorIdState] = useState<number | null>(stored("relay.actor"));
  const [revision, setRevision] = useState(0);
  const [bootError, setBootError] = useState<ApiError | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api<Project[]>("/projects")
      .then((ps) => {
        setProjects(ps);
        if (!ps.find((p) => p.id === projectId) && ps[0]) setProjectIdState(ps[0].id);
        setReady(true);
      })
      .catch((e) => setBootError(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const project = projects.find((p) => p.id === projectId) ?? null;

  useEffect(() => {
    if (!project) return;
    api<Member[]>(`/members?project_id=${project.id}`).then((ms) => {
      setMembers(ms);
      if (!ms.find((m) => m.id === actorId)) {
        const pm = ms.find((m) => /manager/i.test(m.role)) ?? ms[0];
        if (pm) setActorIdState(pm.id);
      }
    }).catch((e) => setBootError(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const setProjectId = useCallback((id: number) => {
    setProjectIdState(id);
    store("relay.project", id);
  }, []);
  const setActorId = useCallback((id: number) => {
    setActorIdState(id);
    store("relay.actor", id);
  }, []);
  const memberName = useCallback(
    (id: number | null | undefined) => (id ? members.find((m) => m.id === id)?.name ?? `#${id}` : "Unassigned"),
    [members],
  );
  const bump = useCallback(() => setRevision((r) => r + 1), []);

  const value = useMemo(() => ({ projects, project, setProjectId, members, memberName, actorId, setActorId, revision,
    bump, bootError, ready }), [projects, project, setProjectId, members, memberName, actorId, setActorId, revision,
    bump, bootError, ready]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}

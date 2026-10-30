export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const future = diff < 0;
  const s = Math.abs(diff);
  const v = s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)}m` : s < 86400 ? `${Math.round(s / 3600)}h`
    : `${Math.round(s / 86400)}d`;
  if (v === "just now") return v;
  return future ? `in ${v}` : `${v} ago`;
}

export const label = (s: string) => s.replace(/_/g, " ");

/** Convert a "type:id" reference into an in-app route. */
export function refRoute(ref: string): string | null {
  const [kind, id] = ref.split(":");
  switch (kind) {
    case "task": return `/tasks/${id}`;
    case "meeting": return `/meetings/${id}`;
    case "decision": return `/knowledge?tab=decisions&decision=${id}`;
    case "document": return `/knowledge?tab=documents&document=${id}`;
    default: return null;
  }
}

export function refLabel(ref: string): string {
  const [kind, id] = ref.split(":");
  if (kind === "decision") return `DEC-${id.padStart(4, "0")}`;
  if (kind === "task") return `TASK-${id}`;
  if (kind === "meeting") return `MTG-${id}`;
  if (kind === "document") return `DOC-${id}`;
  if (kind === "chunk") return `CHUNK-${id}`;
  return ref;
}

export const todayISO = () => new Date().toISOString().slice(0, 10);

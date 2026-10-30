import { useEffect, type ReactNode, type ButtonHTMLAttributes } from "react";
import { AlertTriangle, Inbox, Loader2, X } from "lucide-react";
import { ApiError } from "../lib/api";
import { label } from "../lib/format";

/* ------------------------------------------------------------------ badges */
const TONES = {
  slate: "bg-slate-50 text-slate-600 border-slate-200",
  indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
  cyan: "bg-cyan-50 text-cyan-700 border-cyan-200",
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  rose: "bg-rose-50 text-rose-700 border-rose-200",
  emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
} as const;
const DOTS = { slate: "bg-slate-400", indigo: "bg-indigo-500", cyan: "bg-cyan-500", amber: "bg-amber-500",
  rose: "bg-rose-600", emerald: "bg-emerald-500" } as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = "slate", children, dot = false, className = "" }:
  { tone?: Tone; children: ReactNode; dot?: boolean; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium whitespace-nowrap ${TONES[tone]} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${DOTS[tone]}`} />}
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, Tone> = {
  open: "slate", in_progress: "indigo", blocked: "rose", completed: "cyan", cancelled: "slate",
  active: "cyan", proposed: "amber", superseded: "slate", rejected: "rose",
  pending: "slate", extracted: "amber", approved: "cyan", failed: "rose",
  draft: "amber", current: "cyan",
  confirmed_change: "indigo", marked_proposal: "amber", dismissed: "slate", stale: "slate",
  low: "slate", medium: "indigo", high: "amber", critical: "rose",
  consistent: "cyan", proposal: "amber", potential_conflict: "rose", conditional_change: "amber", revisit: "indigo",
  explicit_replacement: "rose",
};
const STATUS_TEXT: Record<string, string> = { extracted: "awaiting review", pending: "not extracted",
  approved: "approved", active: "active", current: "current version" };

export function StatusBadge({ status, text }: { status: string; text?: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "slate"} dot>{text ?? STATUS_TEXT[status] ?? label(status)}</Badge>;
}

export function IntegrityBadge({ integrity }: { integrity: { state: string; pending_alerts: number } }) {
  switch (integrity.state) {
    case "review_required": return <Badge tone="amber" dot>{integrity.pending_alerts} to review</Badge>;
    case "consistent": return <Badge tone="cyan" dot>No conflicts found</Badge>;
    case "resolved": return <Badge tone="indigo" dot>Reviewed</Badge>;
    case "analysis_failed": return <Badge tone="rose" dot>Analysis failed</Badge>;
    default: return <Badge tone="slate" dot>Not analysed</Badge>;
  }
}

/* ------------------------------------------------------------------ layout */
export function Card({ children, className = "", title, actions, subtitle, padded = true }:
  { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode; subtitle?: ReactNode; padded?: boolean }) {
  return (
    <section className={`min-w-0 bg-surface-card rounded-xl border border-surface-border shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="px-5 py-3.5 flex items-center justify-between gap-3 border-b border-surface-border">
          <div className="flex items-center gap-2.5 min-w-0">
            {typeof title === "string" ? <h3 className="text-sm font-bold text-slate-900">{title}</h3> : title}
            {subtitle && <span className="text-xs text-slate-500 truncate">{subtitle}</span>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </div>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions, badge }:
  { title: string; description?: ReactNode; actions?: ReactNode; badge?: ReactNode }) {
  return (
    <section className="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div className="flex flex-col gap-1 min-w-0">
        <div className="flex items-center gap-2.5 flex-wrap">
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{title}</h1>
          {badge}
        </div>
        {description && <p className="text-xs text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex items-center flex-wrap gap-2.5">{actions}</div>}
    </section>
  );
}

export function MetricCard({ label: l, value, tone = "slate", badge, footnote, icon }:
  { label: string; value: ReactNode; tone?: "slate" | "rose" | "indigo" | "amber"; badge?: ReactNode; footnote?: ReactNode; icon?: ReactNode }) {
  const color = { slate: "text-slate-900", rose: "text-rose-600", indigo: "text-indigo-600", amber: "text-amber-600" }[tone];
  return (
    <div className="min-w-0 bg-surface-card rounded-xl p-5 border border-surface-border shadow-sm flex flex-col justify-between">
      <div className="flex items-center justify-between pb-2 gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{l}</span>
        {badge ?? <span className="text-slate-400">{icon}</span>}
      </div>
      <div className="flex flex-col gap-0.5 mt-2">
        <span className={`text-3xl font-extrabold tracking-tight ${color}`}>{value}</span>
        {footnote && <span className="text-xs text-slate-500 pt-1">{footnote}</span>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ buttons & fields */
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "gradient"; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode;
};
export function Button({ variant = "secondary", size = "md", loading, icon, children, className = "", disabled, ...rest }: BtnProps) {
  const v = {
    primary: "bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm",
    secondary: "bg-white border border-surface-border hover:bg-slate-50 text-slate-700 shadow-sm",
    ghost: "text-slate-500 hover:text-slate-800 hover:bg-slate-100",
    danger: "bg-rose-600 hover:bg-rose-700 text-white shadow-sm",
    gradient: "bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-700 hover:to-cyan-700 text-white shadow-sm shadow-indigo-500/20",
  }[variant];
  const s = size === "sm" ? "h-8 px-3 text-xs" : "h-9 px-3.5 text-xs";
  return (
    <button type="button" disabled={disabled || loading}
      className={`${s} ${v} rounded-lg font-semibold inline-flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 ${className}`}
      {...rest}>
      {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export const inputCls = "w-full h-9 px-3 bg-white rounded-lg border border-surface-border text-slate-900 placeholder:text-slate-400 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-slate-50";
export const textareaCls = "w-full px-3 py-2 bg-white rounded-lg border border-surface-border text-slate-900 placeholder:text-slate-400 text-xs leading-relaxed focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500";

export function Field({ label: l, children, hint, required, htmlFor }:
  { label: string; children: ReactNode; hint?: ReactNode; required?: boolean; htmlFor?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {l}{required && <span className="text-rose-500"> *</span>}
      </label>
      {children}
      {hint && <p className="text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ states */
export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={`w-4 h-4 animate-spin text-indigo-500 ${className}`} />;
}

export function LoadingState({ text = "Loading…" }: { text?: string }) {
  return <div className="flex items-center justify-center gap-2 py-12 text-xs text-slate-500"><Spinner />{text}</div>;
}

export function EmptyState({ title, description, action, icon }:
  { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center gap-2 py-10 px-4">
      <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
        {icon ?? <Inbox className="w-5 h-5" />}
      </div>
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      {description && <p className="text-xs text-slate-500 max-w-md">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error as ApiError;
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50/60 p-4 text-xs">
      <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="font-semibold text-rose-800">{e?.message ?? "Something went wrong."}</p>
        {e?.requestId && <p className="text-rose-500 font-mono text-[10px] mt-1">Request ID {e.requestId}</p>}
      </div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Callout({ tone = "indigo", title, children, icon }:
  { tone?: "indigo" | "amber" | "rose" | "cyan" | "slate"; title?: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  const cls = { indigo: "bg-indigo-50/60 border-indigo-200 text-indigo-900", amber: "bg-amber-50/60 border-amber-200 text-amber-900",
    rose: "bg-rose-50/60 border-rose-200 text-rose-900", cyan: "bg-cyan-50/60 border-cyan-200 text-cyan-900",
    slate: "bg-slate-50 border-surface-border text-slate-800" }[tone];
  return (
    <div className={`flex items-start gap-2.5 rounded-lg border p-3 text-xs ${cls}`}>
      {icon && <span className="shrink-0 mt-0.5">{icon}</span>}
      <div className="flex-1 min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-slate-700 mt-0.5 leading-relaxed">{children}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ modal */
export function Modal({ open, onClose, title, children, footer, wide = false }:
  { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-start sm:items-center justify-center p-4 bg-slate-900/40 backdrop-blur-[2px] overflow-y-auto"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true"
        className={`bg-white rounded-xl shadow-xl border border-surface-border w-full ${wide ? "max-w-3xl" : "max-w-lg"} my-8 flex flex-col max-h-[calc(100vh-4rem)]`}>
        <div className="px-5 py-3.5 flex items-center justify-between border-b border-surface-border">
          <h2 className="text-sm font-bold text-slate-900">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 overflow-y-auto">{children}</div>
        {footer && <div className="px-5 py-3 border-t border-surface-border bg-slate-50/60 rounded-b-xl flex justify-end gap-2 flex-wrap">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", danger, loading, onConfirm, onCancel, children }:
  { open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; loading?: boolean;
    onConfirm: () => void; onCancel: () => void; children?: ReactNode }) {
  return (
    <Modal open={open} onClose={onCancel} title={title}
      footer={<>
        <Button onClick={onCancel}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
      </>}>
      <div className="text-xs text-slate-700 leading-relaxed flex flex-col gap-3">{message}{children}</div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ table & timeline */
export function Table({ head, children, empty }: { head: ReactNode[]; children: ReactNode; empty?: ReactNode }) {
  return (
    <div className="overflow-x-auto w-full">
      <table className="w-full text-left text-xs">
        <thead className="bg-slate-50 text-slate-500 uppercase font-semibold text-[11px] border-b border-surface-border">
          <tr>{head.map((h, i) => <th key={i} className={`py-3 ${i === 0 ? "px-5" : "px-4"} whitespace-nowrap`}>{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-surface-border">{children}</tbody>
      </table>
      {empty}
    </div>
  );
}

export function TimelineItem({ who, when, tone = "slate", children }:
  { who: ReactNode; when: ReactNode; tone?: "cyan" | "indigo" | "slate" | "amber" | "rose"; children: ReactNode }) {
  const dot = { cyan: "bg-cyan-500 ring-cyan-100", indigo: "bg-indigo-600 ring-indigo-100", slate: "bg-slate-400 ring-slate-100",
    amber: "bg-amber-500 ring-amber-100", rose: "bg-rose-500 ring-rose-100" }[tone];
  return (
    <div className="relative pl-6 flex flex-col gap-1">
      <span className={`absolute left-1.5 top-1 w-2.5 h-2.5 rounded-full ring-4 ${dot}`} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-900">{who}</span>
        <span className="font-mono text-[11px] text-slate-400 whitespace-nowrap">{when}</span>
      </div>
      <div className="text-xs text-slate-600">{children}</div>
    </div>
  );
}

export function Timeline({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex flex-col gap-5 pl-1.5">
      <div className="absolute left-2.5 top-2 bottom-2 w-0.5 bg-slate-200" />
      {children}
    </div>
  );
}

export function Quote({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "amber" | "indigo" }) {
  const cls = { slate: "border-slate-300", amber: "border-amber-400", indigo: "border-indigo-400" }[tone];
  return <blockquote className={`border-l-2 ${cls} pl-3 text-xs text-slate-700 italic leading-relaxed`}>“{children}”</blockquote>;
}

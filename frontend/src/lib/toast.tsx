import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import { ApiError } from "./api";

type Toast = { id: number; kind: "success" | "error"; message: string; detail?: string };
const ToastCtx = createContext<{ success: (m: string) => void; error: (e: unknown) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts, { ...t, id }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), t.kind === "error" ? 8000 : 4000);
  }, []);
  const success = useCallback((message: string) => push({ kind: "success", message }), [push]);
  const error = useCallback((e: unknown) => {
    const err = e as ApiError;
    push({ kind: "error", message: err?.message ?? String(e),
      detail: err?.requestId ? `Request ID ${err.requestId}` : undefined });
  }, [push]);

  return (
    <ToastCtx.Provider value={{ success, error }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[min(380px,calc(100vw-2rem))]" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role="status"
            className={`flex items-start gap-2.5 rounded-lg border p-3 shadow-lg bg-white text-xs ${t.kind === "error" ? "border-rose-200" : "border-cyan-200"}`}>
            {t.kind === "error" ? <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              : <CheckCircle2 className="w-4 h-4 text-cyan-600 shrink-0 mt-0.5" />}
            <div className="flex-1 min-w-0">
              <p className="text-slate-800 font-medium break-words">{t.message}</p>
              {t.detail && <p className="text-slate-400 font-mono text-[10px] mt-0.5">{t.detail}</p>}
            </div>
            <button aria-label="Dismiss" onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))}
              className="text-slate-400 hover:text-slate-700"><X className="w-3.5 h-3.5" /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast outside ToastProvider");
  return ctx;
}

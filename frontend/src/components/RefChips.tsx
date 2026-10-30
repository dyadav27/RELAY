import { Link } from "react-router-dom";
import { refLabel, refRoute } from "../lib/format";
import type { BriefItem } from "../lib/types";

export function RefChip({ id }: { id: string }) {
  const route = refRoute(id);
  const cls = "font-mono text-[10px] px-1.5 py-0.5 rounded border bg-indigo-50 border-indigo-200 text-indigo-700";
  return route ? <Link to={route} className={`${cls} hover:bg-indigo-100`}>{refLabel(id)}</Link>
    : <span className={cls}>{refLabel(id)}</span>;
}

export function BriefSection({ title, items, empty = "Nothing recorded." }: { title: string; items: BriefItem[]; empty?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{title}</h4>
      {items.length === 0 ? <p className="text-xs text-slate-400">{empty}</p> : (
        <ul className="flex flex-col gap-1.5">
          {items.map((it, i) => (
            <li key={i} className="text-xs text-slate-700 flex flex-wrap items-start gap-1.5">
              <span className="text-slate-300 mt-[1px]">•</span>
              <span className="flex-1 min-w-[12rem]">{it.text}</span>
              <span className="flex flex-wrap gap-1">{it.refs.map((r) => <RefChip key={r} id={r} />)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

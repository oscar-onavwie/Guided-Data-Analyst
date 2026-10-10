"use client";

import { cx } from "./ui";

export type Stage = "upload" | "profile" | "explore" | "discover" | "report";

export const STAGES: { id: Stage; label: string; hint: string }[] = [
  { id: "upload", label: "Upload", hint: "Load a CSV, Excel file or demo" },
  { id: "profile", label: "Profile", hint: "Structure and data quality" },
  { id: "explore", label: "Explore", hint: "Statistics and charts" },
  { id: "discover", label: "Discover", hint: "Evidence-backed findings" },
  { id: "report", label: "Report", hint: "Export HTML, PDF or CSV" },
];

export function StageNav({ active, onSelect, hasDataset }: { active: Stage; onSelect: (s: Stage) => void; hasDataset: boolean }) {
  return (
    <nav aria-label="Analysis stages" className="md:w-56 md:shrink-0">
      <ol className="flex gap-2 overflow-x-auto pb-1 md:sticky md:top-6 md:flex-col md:gap-1 md:overflow-visible">
        {STAGES.map((s, i) => {
          const disabled = s.id !== "upload" && !hasDataset;
          const current = active === s.id;
          return (
            <li key={s.id} className="shrink-0">
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                disabled={disabled}
                aria-current={current ? "step" : undefined}
                title={disabled ? "Load a dataset first" : s.hint}
                className={cx(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  current ? "bg-teal-700 text-white" : "text-zinc-700 hover:bg-white",
                  disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
                )}
              >
                <span
                  className={cx(
                    "grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-semibold",
                    current ? "bg-white/20 text-white" : "bg-zinc-200 text-zinc-700",
                  )}
                  aria-hidden="true"
                >
                  {i + 1}
                </span>
                <span className="flex flex-col">
                  <span className="font-medium">{s.label}</span>
                  <span className={cx("hidden text-xs md:block", current ? "text-teal-50" : "text-zinc-500")}>
                    {disabled ? "Load a dataset first" : s.hint}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

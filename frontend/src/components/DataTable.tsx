import type { ReactNode } from "react";

/** Scrollable table with a sticky header. Missing cells are shown explicitly, never as blanks or zeros. */
export function DataTable({ columns, rows, caption, numericColumns = [] }: {
  columns: string[];
  rows: ReactNode[][];
  caption: string;
  numericColumns?: number[];
}) {
  return (
    <div className="max-h-[28rem] overflow-auto rounded-lg border border-zinc-200" tabIndex={0} aria-label={caption}>
      <table className="min-w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 z-10 bg-zinc-50">
          <tr>
            {columns.map((c, i) => (
              <th
                key={`${c}-${i}`}
                scope="col"
                className={`whitespace-nowrap border-b border-zinc-200 px-3 py-2 text-left font-semibold text-zinc-700 ${numericColumns.includes(i) ? "text-right" : ""}`}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="odd:bg-white even:bg-zinc-50/60">
              {row.map((cell, i) => (
                <td
                  key={i}
                  className={`max-w-[18rem] truncate whitespace-nowrap border-b border-zinc-100 px-3 py-1.5 text-zinc-800 ${numericColumns.includes(i) ? "text-right tabular-nums" : ""}`}
                >
                  {cell === null || cell === undefined ? <span className="text-xs italic text-zinc-400">missing</span> : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

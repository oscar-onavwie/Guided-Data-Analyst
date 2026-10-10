"use client";

import type { DatasetSummary } from "@/lib/types";
import { formatNumber } from "@/lib/format";
import { Badge, Button } from "./ui";

/** Always-visible indicator of which dataset is loaded (and whether it is demo data). */
export function DatasetStatus({ dataset, onRemove }: { dataset: DatasetSummary | null; onRemove: () => void }) {
  if (!dataset) {
    return (
      <p className="flex items-center gap-2 text-sm text-zinc-500" aria-live="polite">
        <span className="h-2 w-2 rounded-full bg-zinc-300" aria-hidden="true" />
        No dataset loaded
      </p>
    );
  }
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm" aria-live="polite">
      <span className="h-2 w-2 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
      <span className="max-w-[16rem] truncate font-medium" title={dataset.filename}>
        {dataset.filename}
      </span>
      {dataset.sheet && <span className="text-zinc-500">· {dataset.sheet}</span>}
      <span className="text-zinc-500">
        · {formatNumber(dataset.rows)} rows × {dataset.columns} cols
      </span>
      {dataset.is_demo && <Badge tone="amber">DEMO DATA</Badge>}
      <Button variant="ghost" className="px-2 py-1 text-xs" onClick={onRemove} aria-label={`Remove ${dataset.filename} from the server`}>
        Remove
      </Button>
    </div>
  );
}

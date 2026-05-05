import React from "react";

export interface TakeoffTraceEntry {
  label: string;
  value: string;
  source?: string;
}

export interface TakeoffTracePanelProps {
  entries: TakeoffTraceEntry[];
  defaultOpen?: boolean;
}

export default function TakeoffTracePanel({
  entries,
  defaultOpen = false,
}: TakeoffTracePanelProps): JSX.Element {
  return (
    <details
      open={defaultOpen}
      className="rounded-xl border border-slate-200 bg-slate-50 p-4"
    >
      <summary className="cursor-pointer text-sm font-semibold text-slate-800">
        Trace (optional)
      </summary>
      <p className="mt-2 text-sm text-slate-600">
        Shows how this estimate was produced. You can log without opening this.
      </p>
      <ul className="mt-3 space-y-2">
        {entries.map((entry) => (
          <li key={`${entry.label}-${entry.value}`} className="text-sm text-slate-800">
            <span className="font-medium">{entry.label}:</span> {entry.value}
            {entry.source ? (
              <span className="ml-1 text-slate-500">({entry.source})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

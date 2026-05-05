import React from "react";

export interface LogAnywayPayload {
  wideRangeFlag: true;
  loggedAt: string;
}

export interface LogAnywayButtonProps {
  disabled?: boolean;
  onLogAnyway: (payload: LogAnywayPayload) => void;
}

export default function LogAnywayButton({
  disabled = false,
  onLogAnyway,
}: LogAnywayButtonProps): JSX.Element {
  const handleClick = (): void => {
    onLogAnyway({
      wideRangeFlag: true,
      loggedAt: new Date().toISOString(),
    });
  };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={handleClick}
      className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
    >
      Log Anyway
    </button>
  );
}

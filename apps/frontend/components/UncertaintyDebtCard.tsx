import React from "react";

export interface UncertaintyDebtCardProps {
  debtScore: number;
  wideRangeMeals: number;
}

function debtLabel(debtScore: number): string {
  if (debtScore >= 7) {
    return "High";
  }

  if (debtScore >= 4) {
    return "Moderate";
  }

  return "Low";
}

export default function UncertaintyDebtCard({
  debtScore,
  wideRangeMeals,
}: UncertaintyDebtCardProps): JSX.Element {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-base font-semibold text-slate-900">Uncertainty Debt</h3>
      <p className="mt-2 text-sm text-slate-700">
        Debt score: <span className="font-semibold">{debtScore.toFixed(1)}</span> (
        {debtLabel(debtScore)})
      </p>
      <p className="mt-1 text-sm text-slate-700">
        Wide-range logs this week:{" "}
        <span className="font-semibold">{wideRangeMeals}</span>
      </p>
    </section>
  );
}

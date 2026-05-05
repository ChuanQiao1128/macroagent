import React from "react";
import UncertaintyDebtCard from "./UncertaintyDebtCard";

export interface WeeklyReviewCardProps {
  weekLabel: string;
  mealsLogged: number;
  wideRangeMeals: number;
  uncertaintyDebtScore: number;
}

export default function WeeklyReviewCard({
  weekLabel,
  mealsLogged,
  wideRangeMeals,
  uncertaintyDebtScore,
}: WeeklyReviewCardProps): JSX.Element {
  const wideRangeRate =
    mealsLogged > 0 ? `${Math.round((wideRangeMeals / mealsLogged) * 100)}%` : "0%";

  return (
    <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <h2 className="text-base font-semibold text-slate-900">Weekly Review</h2>
      <p className="mt-1 text-sm text-slate-700">{weekLabel}</p>
      <div className="mt-3 grid gap-2 text-sm text-slate-800 sm:grid-cols-2">
        <p>
          Meals logged: <span className="font-medium">{mealsLogged}</span>
        </p>
        <p>
          Wide-range rate: <span className="font-medium">{wideRangeRate}</span>
        </p>
      </div>
      <div className="mt-3">
        <UncertaintyDebtCard
          debtScore={uncertaintyDebtScore}
          wideRangeMeals={wideRangeMeals}
        />
      </div>
    </section>
  );
}

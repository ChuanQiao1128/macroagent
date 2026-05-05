import React from "react";

export interface EstimateRangeCardProps {
  bestEstimateKcal: number;
  likelyLowKcal: number;
  likelyHighKcal: number;
  confidenceLabel: string;
  mainUncertaintyDriver: string;
}

const kcalFormatter = new Intl.NumberFormat("en-US");

function formatKcal(value: number): string {
  return `${kcalFormatter.format(Math.round(value))} kcal`;
}

export default function EstimateRangeCard({
  bestEstimateKcal,
  likelyLowKcal,
  likelyHighKcal,
  confidenceLabel,
  mainUncertaintyDriver,
}: EstimateRangeCardProps): JSX.Element {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">Estimate</h2>
      <dl className="mt-3 space-y-2">
        <div className="flex items-center justify-between">
          <dt className="text-sm text-slate-600">Best estimate</dt>
          <dd className="text-sm font-medium text-slate-900">
            {formatKcal(bestEstimateKcal)}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-sm text-slate-600">Likely range</dt>
          <dd className="text-sm font-medium text-slate-900">
            {formatKcal(likelyLowKcal)} to {formatKcal(likelyHighKcal)}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-sm text-slate-600">Confidence</dt>
          <dd className="text-sm font-medium text-slate-900">{confidenceLabel}</dd>
        </div>
        <div>
          <dt className="text-sm text-slate-600">Main uncertainty driver</dt>
          <dd className="mt-1 text-sm text-slate-900">{mainUncertaintyDriver}</dd>
        </div>
      </dl>
    </section>
  );
}

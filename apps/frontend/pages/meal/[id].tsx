import React, { useMemo, useState } from "react";
import ClarificationPrompt, {
  type ClarificationQuestion,
} from "../../components/ClarificationPrompt";
import EstimateRangeCard from "../../components/EstimateRangeCard";
import LogAnywayButton, {
  type LogAnywayPayload,
} from "../../components/LogAnywayButton";
import TakeoffTracePanel from "../../components/TakeoffTracePanel";
import WeeklyReviewCard from "../../components/WeeklyReviewCard";

type MealReviewState = "CLARIFY" | "READY" | "LOGGED";

interface MealLogRecord {
  mealId: string;
  loggedAt: string;
  wideRangeFlag: boolean;
  selectedClarification: string | null;
}

const CLARIFICATION_QUESTIONS: ClarificationQuestion[] = [
  {
    id: "oil-usage",
    prompt: "Was extra cooking oil added after plating?",
    options: ["No", "A little", "Yes"],
  },
  {
    id: "unused-question",
    prompt: "This will not render because only one clarification is shown.",
    options: ["N/A"],
  },
];

const TRACE_ENTRIES = [
  { label: "Portion estimate", value: "1.3 servings", source: "vision+history" },
  { label: "Energy density", value: "1.8 kcal/g", source: "USDA seed + fallback" },
  { label: "Range driver", value: "Unknown sauce volume", source: "takeoff trace" },
];

export default function MealDetailPage(): JSX.Element {
  const mealId = "meal-001";
  const [reviewState, setReviewState] = useState<MealReviewState>("CLARIFY");
  const [selectedClarification, setSelectedClarification] = useState<string | null>(
    null
  );
  const [logRecord, setLogRecord] = useState<MealLogRecord | null>(null);
  const [mealsLoggedThisWeek, setMealsLoggedThisWeek] = useState<number>(11);
  const [wideRangeMealsThisWeek, setWideRangeMealsThisWeek] = useState<number>(2);

  const uncertaintyDebtScore = useMemo(() => {
    const base = 2.5;
    const debt = base + wideRangeMealsThisWeek * 0.8;
    return Math.min(10, debt);
  }, [wideRangeMealsThisWeek]);

  const finalizeLog = (wideRangeFlag: boolean, loggedAt: string): void => {
    setLogRecord({
      mealId,
      loggedAt,
      wideRangeFlag,
      selectedClarification,
    });
    setMealsLoggedThisWeek((current) => current + 1);
    if (wideRangeFlag) {
      setWideRangeMealsThisWeek((current) => current + 1);
    }
    setReviewState("LOGGED");
  };

  const handleClarificationSelect = (_questionId: string, option: string): void => {
    setSelectedClarification(option);
    setReviewState("READY");
  };

  const handleLogMeal = (): void => {
    finalizeLog(false, new Date().toISOString());
  };

  const handleLogAnyway = ({ wideRangeFlag, loggedAt }: LogAnywayPayload): void => {
    finalizeLog(wideRangeFlag, loggedAt);
  };

  return (
    <main className="mx-auto max-w-2xl space-y-4 px-4 py-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Meal Entry</h1>
        <p className="mt-1 text-sm text-slate-700">Meal ID: {mealId}</p>
      </header>

      <EstimateRangeCard
        bestEstimateKcal={680}
        likelyLowKcal={540}
        likelyHighKcal={860}
        confidenceLabel="Medium"
        mainUncertaintyDriver="Sauce and oil quantity"
        primarySource="USDA seed + meal history"
      />

      {reviewState === "CLARIFY" ? (
        <ClarificationPrompt
          questions={CLARIFICATION_QUESTIONS}
          onSelectOption={handleClarificationSelect}
        />
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Log Meal</h2>
        <p className="mt-2 text-sm text-slate-700">
          You can log this meal now. Trace details are optional.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleLogMeal}
            disabled={reviewState !== "READY"}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Log Meal
          </button>
          {reviewState === "CLARIFY" ? (
            <LogAnywayButton
              disabled={reviewState === "LOGGED"}
              onLogAnyway={handleLogAnyway}
            />
          ) : null}
        </div>
        {selectedClarification ? (
          <p className="mt-2 text-sm text-slate-600">
            Clarification captured: {selectedClarification}
          </p>
        ) : null}
        {logRecord ? (
          <p className="mt-2 text-sm text-slate-700">
            Logged at {new Date(logRecord.loggedAt).toLocaleString()} with wide-range
            flag: <span className="font-medium">{String(logRecord.wideRangeFlag)}</span>
          </p>
        ) : null}
      </section>

      <TakeoffTracePanel entries={TRACE_ENTRIES} />

      <WeeklyReviewCard
        weekLabel="Current week"
        mealsLogged={mealsLoggedThisWeek}
        wideRangeMeals={wideRangeMealsThisWeek}
        uncertaintyDebtScore={uncertaintyDebtScore}
      />
    </main>
  );
}

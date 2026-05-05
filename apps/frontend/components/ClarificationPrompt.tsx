import React from "react";

export interface ClarificationQuestion {
  id: string;
  prompt: string;
  options: string[];
}

export interface ClarificationPromptProps {
  questions: ClarificationQuestion[];
  onSelectOption: (questionId: string, option: string) => void;
}

export default function ClarificationPrompt({
  questions,
  onSelectOption,
}: ClarificationPromptProps): JSX.Element | null {
  const firstQuestion = questions[0];

  if (!firstQuestion) {
    return null;
  }

  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <h2 className="text-base font-semibold text-slate-900">Quick Clarification</h2>
      <p className="mt-2 text-sm text-slate-800">{firstQuestion.prompt}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {firstQuestion.options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onSelectOption(firstQuestion.id, option)}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-slate-100"
          >
            {option}
          </button>
        ))}
      </div>
    </section>
  );
}

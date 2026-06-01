"use client";

import { useActionState } from "react";
import { createProject, type CreateProjectState } from "@/app/(app)/project/actions";
import { Callout } from "@/components/ui/Callout";

const TIERS = [
  { key: "academic", label: "Academic" },
  { key: "government", label: "Government" },
  { key: "news", label: "News" },
  { key: "industry", label: "Industry" },
  { key: "social_media", label: "Social media" },
] as const;

export function NewProjectForm() {
  const [state, action, isPending] = useActionState<CreateProjectState, FormData>(
    createProject,
    undefined
  );

  return (
    <form action={action} className="flex flex-col gap-6">
      {state?.error && (
        <Callout variant="coral">{state.error}</Callout>
      )}

      <div>
        <label
          className="block text-title-sm text-ink mb-2"
          htmlFor="research_question"
        >
          Research question
        </label>
        <textarea
          id="research_question"
          name="research_question"
          required
          rows={4}
          placeholder="e.g. What are the most effective strategies for reducing urban heat islands in mid-sized American cities?"
          className="w-full px-4 py-3 bg-canvas text-ink text-body-md rounded-md border border-hairline placeholder:text-muted-soft focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition-colors resize-none"
        />
      </div>

      <div>
        <p className="text-title-sm text-ink mb-3">Source tiers</p>
        <div className="flex flex-wrap gap-4">
          {TIERS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                name={key}
                defaultChecked={key === "academic" || key === "government"}
                className="accent-primary w-4 h-4"
              />
              <span className="text-body-md text-ink">{label}</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <label
          className="block text-title-sm text-ink mb-2"
          htmlFor="recency_months"
        >
          Recency filter{" "}
          <span className="text-muted font-normal">(months, optional)</span>
        </label>
        <input
          id="recency_months"
          name="recency_months"
          type="number"
          min="1"
          max="240"
          placeholder="Leave blank for all dates"
          className="w-56 h-10 px-4 bg-canvas text-ink text-body-md rounded-md border border-hairline placeholder:text-muted-soft focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition-colors"
        />
      </div>

      <div>
        <button
          type="submit"
          disabled={isPending}
          className="h-10 px-6 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors disabled:bg-primary-disabled disabled:text-muted disabled:cursor-not-allowed"
        >
          {isPending ? "Creating…" : "Create project"}
        </button>
      </div>
    </form>
  );
}

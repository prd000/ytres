"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { SourceTierSettings } from "@/lib/data/types";

export type CreateProjectState = { error: string } | undefined;

export async function createProject(
  _prev: CreateProjectState,
  formData: FormData
): Promise<CreateProjectState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  const researchQuestion = (formData.get("research_question") as string).trim();
  if (!researchQuestion) return { error: "Research question is required." };

  const recencyRaw = formData.get("recency_months") as string;
  const sourceTierSettings: SourceTierSettings = {
    academic: formData.get("academic") === "on",
    government: formData.get("government") === "on",
    news: formData.get("news") === "on",
    industry: formData.get("industry") === "on",
    recencyMonths: recencyRaw ? Number(recencyRaw) : null,
  };

  const { data, error } = await supabase
    .from("projects")
    .insert({
      owner_id: user.id,
      research_question: researchQuestion,
      source_tier_settings: sourceTierSettings,
      status: "draft",
    })
    .select("id")
    .single();

  if (error) return { error: error.message };
  redirect(`/project/${data.id}/plan`);
}

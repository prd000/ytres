"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import type { SourceTierSettings } from "@/lib/data/types";

export type CreateProjectState = { error: string } | undefined;
export type RegeneratePlanState = { error: string } | undefined;
export type ApprovePlanState = { error: string } | undefined;
export type DeleteProjectState = { error: string } | undefined;

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
    socialMedia: formData.get("social_media") === "on",
    recencyMonths: recencyRaw ? Number(recencyRaw) : null,
  };

  const { data, error } = await supabase
    .from("projects")
    .insert({
      owner_id: user.id,
      research_question: researchQuestion,
      source_tier_settings: sourceTierSettings,
      status: "planning",
    })
    .select("id")
    .single();

  if (error) return { error: error.message };

  const { error: jobError } = await supabase.from("jobs").insert({
    project_id: data.id,
    type: "generate_plan",
    payload: { project_id: data.id },
  });

  if (jobError) return { error: jobError.message };

  redirect(`/project/${data.id}/plan`);
}

export async function regeneratePlan(
  projectId: string,
  _prev: RegeneratePlanState,
  formData: FormData
): Promise<RegeneratePlanState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  const feedback = (formData.get("feedback") as string | null)?.trim() || null;

  const { error: statusError } = await supabase
    .from("projects")
    .update({ status: "planning" })
    .eq("id", projectId);

  if (statusError) return { error: statusError.message };

  const { error: jobError } = await supabase.from("jobs").insert({
    project_id: projectId,
    type: "generate_plan",
    payload: { project_id: projectId, feedback },
  });

  if (jobError) return { error: jobError.message };

  revalidatePath(`/project/${projectId}/plan`);
}

export async function approvePlan(
  projectId: string,
  _prev: ApprovePlanState,
  _formData: FormData
): Promise<ApprovePlanState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  const { error } = await supabase
    .from("projects")
    .update({ status: "researching" })
    .eq("id", projectId);

  if (error) return { error: error.message };

  // Fetch subtopic ids so we can enqueue one research job per subtopic
  const { data: subtopics, error: subtopicError } = await supabase
    .from("subtopics")
    .select("id")
    .eq("project_id", projectId);

  if (subtopicError) return { error: subtopicError.message };
  if (!subtopics || subtopics.length === 0) {
    return { error: "No subtopics found — regenerate the plan first." };
  }

  const jobs = subtopics.map((sub: { id: string }) => ({
    project_id: projectId,
    type: "research_subtopic",
    payload: { project_id: projectId, subtopic_id: sub.id },
  }));

  const { error: jobError } = await supabase.from("jobs").insert(jobs);
  if (jobError) return { error: jobError.message };

  revalidatePath(`/project/${projectId}/plan`);
}

export async function deleteProject(
  projectId: string,
  _prev: DeleteProjectState,
  _formData: FormData
): Promise<DeleteProjectState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  // Best-effort: stop any in-flight worker job so the handler exits gracefully
  // instead of erroring once the cascade removes its job row below.
  await supabase.rpc("cancel_project_jobs", { p_project_id: projectId });

  // RLS (projects_delete: owner_id = auth.uid()) gates this to the owner; the
  // `on delete cascade` FKs purge all subtopics, sources, chunks, chat, and reports.
  const { error } = await supabase.from("projects").delete().eq("id", projectId);
  if (error) return { error: error.message };

  revalidatePath("/dashboard");
  redirect("/dashboard");
}

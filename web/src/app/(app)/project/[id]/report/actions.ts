"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

export type GenerateReportState = { error: string } | undefined;

export async function generateReport(
  projectId: string,
  options: {
    mode: "curated" | "auto";
    sourceIds: string[];
    instructions?: string;
  }
): Promise<GenerateReportState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  const { error: jobError } = await supabase.from("jobs").insert({
    project_id: projectId,
    type: "generate_report",
    payload: {
      project_id: projectId,
      mode: options.mode,
      source_ids: options.sourceIds,
      instructions: options.instructions ?? null,
    },
  });

  if (jobError) return { error: jobError.message };

  revalidatePath(`/project/${projectId}/report`);
}

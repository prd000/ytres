"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

export type SendChatMessageState = { error: string } | undefined;
export type SpawnResearchState = { error: string } | undefined;

export async function sendChatMessage(
  projectId: string,
  question: string
): Promise<SendChatMessageState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  const trimmed = question.trim();
  if (!trimmed) return { error: "Question cannot be empty." };

  // Insert user chat_messages row — RLS (chat_messages_insert: can_write_project) gates this.
  const { error: msgError } = await supabase.from("chat_messages").insert({
    project_id: projectId,
    role: "user",
    content: trimmed,
    citations: [],
  });
  if (msgError) return { error: msgError.message };

  // Enqueue the chat_respond job — RLS (jobs_insert: can_write_project) gates this.
  const { error: jobError } = await supabase.from("jobs").insert({
    project_id: projectId,
    type: "chat_respond",
    payload: { project_id: projectId, question: trimmed },
  });
  if (jobError) return { error: jobError.message };

  revalidatePath(`/project/${projectId}/chat`);
}

export async function spawnResearchFromChat(
  projectId: string,
  question: string
): Promise<SpawnResearchState> {
  const supabase = await createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();
  if (authError || !user) return { error: "Not authenticated." };

  // Insert a chat-spawned subtopic. wave=99 is a sentinel outside the coordinator
  // barrier range (max wave=2) — belt-and-suspenders alongside the barrier's
  // project.status='researching' guard, which already prevents coordinator re-trigger.
  const { data: subtopic, error: subtopicError } = await supabase
    .from("subtopics")
    .insert({
      project_id: projectId,
      title: question.slice(0, 120),
      information_objective: `Research triggered from chat: ${question}`,
      source_tier_preferences: ["news", "industry", "academic"],
      wave: 99,
    })
    .select("id")
    .single();

  if (subtopicError) return { error: subtopicError.message };

  const { error: jobError } = await supabase.from("jobs").insert({
    project_id: projectId,
    type: "research_subtopic",
    payload: { project_id: projectId, subtopic_id: subtopic.id },
  });
  if (jobError) return { error: jobError.message };

  revalidatePath(`/project/${projectId}/research`);
}

import "server-only";
import { createClient } from "@/lib/supabase/server";
import type {
  Project,
  Subtopic,
  Source,
  WorkerActivity,
  ChatMessage,
  Report,
} from "./types";

// ─── Row → domain mappers ─────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapProject(row: any): Project {
  return {
    id: row.id,
    researchQuestion: row.research_question,
    status: row.status,
    sourceTierSettings: row.source_tier_settings,
    ownerId: row.owner_id,
    lastUpdated: new Date(row.updated_at),
    createdAt: new Date(row.created_at),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapSubtopic(row: any): Subtopic {
  return {
    id: row.id,
    projectId: row.project_id,
    title: row.title,
    informationObjective: row.information_objective,
    sourceTierPreferences: row.source_tier_preferences,
    status: row.status,
    sortOrder: row.sort_order,
    wave: row.wave ?? 0,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapSource(row: any): Source {
  return {
    id: row.id,
    projectId: row.project_id,
    subtopicIds: (row.source_subtopics ?? []).map(
      (s: { subtopic_id: string }) => s.subtopic_id
    ),
    url: row.url,
    title: row.title,
    fullText: row.full_text,
    tier: row.tier,
    keyTakeaway: row.key_takeaway,
    scores: {
      relevance: row.score_relevance,
      credibility: row.score_credibility,
      uniqueness: row.score_uniqueness,
      actionability: row.score_actionability,
    },
    storedAt: new Date(row.stored_at),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapWorkerActivity(row: any): WorkerActivity {
  return {
    subtopicId: row.subtopic_id,
    latestActivity: row.latest_activity,
    sourcesStored: row.sources_stored,
    status: row.status,
    whyNothingReport: row.why_nothing_report,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapChatMessage(row: any): ChatMessage {
  return {
    id: row.id,
    projectId: row.project_id,
    role: row.role,
    content: row.content,
    citations: row.citations ?? [],
    confidence: row.confidence ?? undefined,
    createdAt: new Date(row.created_at),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapReport(row: any): Report {
  return {
    id: row.id,
    projectId: row.project_id,
    markdown: row.markdown,
    sourceRefs: row.source_refs,
    generatedAt: new Date(row.generated_at),
  };
}

// ─── Public data-access API ───────────────────────────────────────────────────

export async function getProjects(): Promise<Project[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .order("updated_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map(mapProject);
}

export async function getProject(id: string): Promise<Project | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (error) throw error;
  return data ? mapProject(data) : null;
}

export async function getSubtopics(projectId: string): Promise<Subtopic[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("subtopics")
    .select("*")
    .eq("project_id", projectId)
    .order("sort_order");
  if (error) throw error;
  return (data ?? []).map(mapSubtopic);
}

export async function getSources(projectId: string): Promise<Source[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("sources")
    .select("*, source_subtopics(subtopic_id)")
    .eq("project_id", projectId);
  if (error) throw error;
  return (data ?? []).map(mapSource);
}

export async function getWorkerActivity(
  projectId: string
): Promise<WorkerActivity[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("worker_activity")
    .select("*")
    .eq("project_id", projectId);
  if (error) throw error;
  return (data ?? []).map(mapWorkerActivity);
}

export async function getChatMessages(
  projectId: string
): Promise<ChatMessage[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("chat_messages")
    .select("*")
    .eq("project_id", projectId)
    .order("created_at");
  if (error) throw error;
  return (data ?? []).map(mapChatMessage);
}

export async function getReport(projectId: string): Promise<Report | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("reports")
    .select("*")
    .eq("project_id", projectId)
    .order("generated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data ? mapReport(data) : null;
}

export async function getActiveReportJob(projectId: string): Promise<boolean> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("jobs")
    .select("id")
    .eq("project_id", projectId)
    .eq("type", "generate_report")
    .in("status", ["queued", "running"])
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data !== null;
}

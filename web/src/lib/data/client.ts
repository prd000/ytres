import {
  PROJECTS,
  SUBTOPICS,
  SOURCES,
  WORKER_ACTIVITY,
  CHAT_MESSAGES,
  REPORTS,
} from "./fixtures";
import type {
  Project,
  Subtopic,
  Source,
  WorkerActivity,
  ChatMessage,
  Report,
} from "./types";

/* All functions are async so they drop-in replace with real Supabase/fetch calls
   in Phases 1/2 without any call-site changes. */

export async function getProjects(): Promise<Project[]> {
  return PROJECTS;
}

export async function getProject(id: string): Promise<Project | null> {
  return PROJECTS.find((p) => p.id === id) ?? null;
}

export async function getSubtopics(projectId: string): Promise<Subtopic[]> {
  return SUBTOPICS.filter((s) => s.projectId === projectId).sort(
    (a, b) => a.sortOrder - b.sortOrder
  );
}

export async function getSources(projectId: string): Promise<Source[]> {
  return SOURCES.filter((s) => s.projectId === projectId);
}

export async function getWorkerActivity(
  projectId: string
): Promise<WorkerActivity[]> {
  const subtopicIds = SUBTOPICS.filter((s) => s.projectId === projectId).map(
    (s) => s.id
  );
  return WORKER_ACTIVITY.filter((a) => subtopicIds.includes(a.subtopicId));
}

export async function getChatMessages(projectId: string): Promise<ChatMessage[]> {
  return CHAT_MESSAGES.filter((m) => m.projectId === projectId).sort(
    (a, b) => a.createdAt.getTime() - b.createdAt.getTime()
  );
}

export async function getReport(projectId: string): Promise<Report | null> {
  return REPORTS.find((r) => r.projectId === projectId) ?? null;
}

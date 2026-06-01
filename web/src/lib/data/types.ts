export type ProjectStatus = "draft" | "planning" | "researching" | "complete" | "cancelled";
export type SourceTier = "academic" | "government" | "news" | "industry" | "social_media";
export type SubtopicStatus = "queued" | "running" | "complete" | "failed" | "cancelled";
export type ChatRole = "user" | "assistant";

export interface SourceTierSettings {
  academic: boolean;
  government: boolean;
  news: boolean;
  industry: boolean;
  socialMedia: boolean;
  recencyMonths: number | null;
}

export interface Project {
  id: string;
  researchQuestion: string;
  status: ProjectStatus;
  sourceTierSettings: SourceTierSettings;
  ownerId: string;
  lastUpdated: Date;
  createdAt: Date;
}

export interface Subtopic {
  id: string;
  projectId: string;
  title: string;
  informationObjective: string;
  sourceTierPreferences: SourceTier[];
  status: SubtopicStatus;
  sortOrder: number;
}

export interface SourceScores {
  relevance: number;
  credibility: number;
  uniqueness: number;
  actionability: number;
}

export interface Source {
  id: string;
  projectId: string;
  subtopicIds: string[];
  url: string;
  title: string;
  fullText: string;
  tier: SourceTier;
  keyTakeaway: string;
  scores: SourceScores;
  storedAt: Date;
}

export interface WorkerActivity {
  subtopicId: string;
  latestActivity: string;
  sourcesStored: number;
  status: SubtopicStatus;
  whyNothingReport: string | null;
}

export interface Citation {
  sourceId: string;
  sourceTitle: string;
  url: string;
}

export interface ChatMessage {
  id: string;
  projectId: string;
  role: ChatRole;
  content: string;
  citations: Citation[];
  createdAt: Date;
}

export interface Report {
  id: string;
  projectId: string;
  markdown: string;
  sourceRefs: string[];
  generatedAt: Date;
}

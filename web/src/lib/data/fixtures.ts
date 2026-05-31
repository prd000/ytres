import {
  Project,
  Subtopic,
  Source,
  WorkerActivity,
  ChatMessage,
  Report,
} from "./types";

/* ─── Projects ────────────────────────────────────────────────────────────── */

export const PROJECTS: Project[] = [
  {
    id: "proj-1",
    researchQuestion: "What are the most effective strategies for reducing urban heat islands in mid-sized American cities?",
    status: "complete",
    sourceTierSettings: {
      academic: true,
      government: true,
      news: false,
      industry: false,
      recencyMonths: 36,
    },
    ownerId: "user-1",
    lastUpdated: new Date("2026-05-20"),
    createdAt: new Date("2026-05-10"),
  },
  {
    id: "proj-2",
    researchQuestion: "How are large language models being applied to drug discovery and what are the key limitations?",
    status: "researching",
    sourceTierSettings: {
      academic: true,
      government: false,
      news: false,
      industry: true,
      recencyMonths: 24,
    },
    ownerId: "user-1",
    lastUpdated: new Date("2026-05-29"),
    createdAt: new Date("2026-05-27"),
  },
  {
    id: "proj-3",
    researchQuestion: "What governance frameworks exist for autonomous vehicle deployment in urban environments?",
    status: "planning",
    sourceTierSettings: {
      academic: true,
      government: true,
      news: true,
      industry: false,
      recencyMonths: 18,
    },
    ownerId: "user-1",
    lastUpdated: new Date("2026-05-28"),
    createdAt: new Date("2026-05-28"),
  },
  {
    id: "proj-4",
    researchQuestion: "What is the current state of alternative protein production and its environmental impact?",
    status: "draft",
    sourceTierSettings: {
      academic: true,
      government: false,
      news: true,
      industry: true,
      recencyMonths: null,
    },
    ownerId: "user-1",
    lastUpdated: new Date("2026-05-25"),
    createdAt: new Date("2026-05-25"),
  },
  {
    id: "proj-5",
    researchQuestion: "How effective are community land trusts at preserving affordable housing in gentrifying neighborhoods?",
    status: "cancelled",
    sourceTierSettings: {
      academic: true,
      government: true,
      news: false,
      industry: false,
      recencyMonths: 60,
    },
    ownerId: "user-1",
    lastUpdated: new Date("2026-05-15"),
    createdAt: new Date("2026-05-12"),
  },
];

/* ─── Subtopics ───────────────────────────────────────────────────────────── */

export const SUBTOPICS: Subtopic[] = [
  /* proj-1 (complete) */
  {
    id: "sub-1-1",
    projectId: "proj-1",
    title: "Reflective pavements and cool roofs",
    informationObjective: "Identify the documented temperature reduction from high-albedo surfaces, cost ranges, and city-scale deployment case studies.",
    sourceTierPreferences: ["academic", "government"],
    status: "complete",
    sortOrder: 1,
  },
  {
    id: "sub-1-2",
    projectId: "proj-1",
    title: "Urban tree canopy expansion",
    informationObjective: "Understand evapotranspiration effects, species selection for climate resilience, and implementation costs per city block.",
    sourceTierPreferences: ["academic", "government"],
    status: "complete",
    sortOrder: 2,
  },
  {
    id: "sub-1-3",
    projectId: "proj-1",
    title: "Green infrastructure and stormwater integration",
    informationObjective: "Examine co-benefits of green roofs and permeable paving for both thermal regulation and stormwater management.",
    sourceTierPreferences: ["academic"],
    status: "complete",
    sortOrder: 3,
  },
  {
    id: "sub-1-4",
    projectId: "proj-1",
    title: "Policy and funding mechanisms",
    informationObjective: "Survey federal grants, municipal ordinances, and public-private partnership models that have successfully funded UHI interventions.",
    sourceTierPreferences: ["government"],
    status: "complete",
    sortOrder: 4,
  },

  /* proj-2 (researching) */
  {
    id: "sub-2-1",
    projectId: "proj-2",
    title: "Protein structure prediction for drug targets",
    informationObjective: "Assess AlphaFold and similar models' impact on identifying novel druggable targets and how labs are using these predictions.",
    sourceTierPreferences: ["academic"],
    status: "complete",
    sortOrder: 1,
  },
  {
    id: "sub-2-2",
    projectId: "proj-2",
    title: "Molecule generation and virtual screening",
    informationObjective: "Evaluate generative models for de novo molecule design, comparing hit rates versus traditional HTS approaches.",
    sourceTierPreferences: ["academic", "industry"],
    status: "running",
    sortOrder: 2,
  },
  {
    id: "sub-2-3",
    projectId: "proj-2",
    title: "Clinical trial outcome prediction",
    informationObjective: "Identify LLM applications in predicting Phase II/III trial success and what data inputs drive accuracy.",
    sourceTierPreferences: ["academic", "industry"],
    status: "queued",
    sortOrder: 3,
  },
  {
    id: "sub-2-4",
    projectId: "proj-2",
    title: "Regulatory and safety limitations",
    informationObjective: "Document FDA/EMA concerns about AI-generated candidates, interpretability requirements, and hallucination risks in biochemical contexts.",
    sourceTierPreferences: ["government", "industry"],
    status: "queued",
    sortOrder: 4,
  },

  /* proj-3 (planning) */
  {
    id: "sub-3-1",
    projectId: "proj-3",
    title: "Federal regulatory frameworks",
    informationObjective: "Survey NHTSA and DOT rules for AV testing and deployment, including recent rulemaking activity.",
    sourceTierPreferences: ["government"],
    status: "queued",
    sortOrder: 1,
  },
  {
    id: "sub-3-2",
    projectId: "proj-3",
    title: "State and municipal approaches",
    informationObjective: "Compare how California, Texas, and Arizona have approached AV deployment permits and liability frameworks.",
    sourceTierPreferences: ["government", "news"],
    status: "queued",
    sortOrder: 2,
  },
];

/* ─── Sources ──────────────────────────────────────────────────────────────── */

export const SOURCES: Source[] = [
  /* proj-1 sources */
  {
    id: "src-1",
    projectId: "proj-1",
    subtopicIds: ["sub-1-1"],
    url: "https://www.epa.gov/heat-islands/using-cool-roofs-reduce-heat-islands",
    title: "Using Cool Roofs to Reduce Heat Islands — EPA",
    fullText: "Cool roofs are one of the most cost-effective strategies for reducing urban heat islands...",
    tier: "government",
    keyTakeaway: "Cool roofs can reduce rooftop temperatures by up to 50°F and city-wide temperatures by 1–5°F depending on adoption rates, with installed costs of $0.75–$3.00 per square foot.",
    scores: { relevance: 5, credibility: 5, uniqueness: 4, actionability: 5 },
    storedAt: new Date("2026-05-18"),
  },
  {
    id: "src-2",
    projectId: "proj-1",
    subtopicIds: ["sub-1-1"],
    url: "https://doi.org/10.1016/j.enbuild.2024.001",
    title: "High-albedo pavements: meta-analysis of field studies 2015–2024",
    fullText: "A systematic review of 47 field studies measuring surface and ambient temperature reductions...",
    tier: "academic",
    keyTakeaway: "Field studies show reflective pavements reduce surface temperatures by 10–25°F on average but ambient cooling effect is modest (0.2–1.0°F) unless deployed at district scale.",
    scores: { relevance: 5, credibility: 5, uniqueness: 5, actionability: 3 },
    storedAt: new Date("2026-05-18"),
  },
  {
    id: "src-3",
    projectId: "proj-1",
    subtopicIds: ["sub-1-2"],
    url: "https://doi.org/10.1038/s41558-023-01234-5",
    title: "Urban tree canopy and heat mitigation in North American cities",
    fullText: "Analysis of 38 mid-sized US cities showed a strong inverse relationship between canopy cover and peak summer temperatures...",
    tier: "academic",
    keyTakeaway: "Each 1% increase in urban canopy cover correlates with a 0.14°F reduction in mean summer temperature; cities with 20–30% canopy cover see the most cost-effective heat reduction.",
    scores: { relevance: 5, credibility: 5, uniqueness: 4, actionability: 4 },
    storedAt: new Date("2026-05-19"),
  },
  {
    id: "src-4",
    projectId: "proj-1",
    subtopicIds: ["sub-1-2", "sub-1-3"],
    url: "https://treesforclimate.gov/urban-forestry-toolkit",
    title: "Urban Forestry Toolkit — USDA Forest Service",
    fullText: "This toolkit provides municipal planners with species selection guides, cost estimation frameworks, and maintenance protocols...",
    tier: "government",
    keyTakeaway: "USDA framework recommends 30–40% canopy targets for mid-sized cities and identifies 15 climate-resilient species by USDA hardiness zone, with maintenance cost averaging $125/tree/year.",
    scores: { relevance: 4, credibility: 5, uniqueness: 3, actionability: 5 },
    storedAt: new Date("2026-05-19"),
  },
  {
    id: "src-5",
    projectId: "proj-1",
    subtopicIds: ["sub-1-3"],
    url: "https://doi.org/10.1016/j.landurbplan.2024.002",
    title: "Green roofs as thermal and hydrological co-benefit infrastructure",
    fullText: "This study quantifies both temperature reduction and stormwater retention capacity across 12 US cities...",
    tier: "academic",
    keyTakeaway: "Green roofs reduce local rooftop temperatures by 15–35°F and retain 60–80% of precipitation events under 2 inches, but high installation costs ($10–$25/sqft) limit adoption without subsidy.",
    scores: { relevance: 4, credibility: 5, uniqueness: 4, actionability: 3 },
    storedAt: new Date("2026-05-20"),
  },
  {
    id: "src-6",
    projectId: "proj-1",
    subtopicIds: ["sub-1-4"],
    url: "https://www.hud.gov/program_offices/community_planning/climate",
    title: "HUD Community Development Block Grants for Climate Resilience",
    fullText: "CDBG-DR and CDBG-MIT programs provide flexible funding for climate adaptation in low-moderate income areas...",
    tier: "government",
    keyTakeaway: "HUD's CDBG-MIT allocations have funded 43 UHI mitigation projects totaling $380M since 2021, with per-project grants ranging from $2M to $18M for qualifying municipalities.",
    scores: { relevance: 3, credibility: 5, uniqueness: 2, actionability: 5 },
    storedAt: new Date("2026-05-20"),
  },

  /* proj-2 sources (sub-2-1 complete, sub-2-2 running) */
  {
    id: "src-7",
    projectId: "proj-2",
    subtopicIds: ["sub-2-1"],
    url: "https://doi.org/10.1038/s41586-024-07487-w",
    title: "AlphaFold3 and the expansion of the druggable proteome",
    fullText: "Analysis of 250,000 predicted structures reveals 8,400 previously inaccessible binding pockets...",
    tier: "academic",
    keyTakeaway: "AlphaFold3 has expanded the tractable protein structure space by ~23%, uncovering 8,400 new potential binding sites across 1,200 disease-relevant proteins, with particularly high impact on intrinsically disordered regions.",
    scores: { relevance: 5, credibility: 5, uniqueness: 5, actionability: 4 },
    storedAt: new Date("2026-05-28"),
  },
  {
    id: "src-8",
    projectId: "proj-2",
    subtopicIds: ["sub-2-1"],
    url: "https://doi.org/10.1021/acs.jmedchem.2024.001",
    title: "Structure-guided drug design outcomes: AlphaFold vs. X-ray crystallography",
    fullText: "Head-to-head comparison of 120 drug discovery programs using AI-predicted vs. experimentally determined structures...",
    tier: "academic",
    keyTakeaway: "Campaigns using AlphaFold2-predicted structures yielded lead compounds at 78% the rate of X-ray campaigns, but with 3× faster timelines and 60% lower cost, suggesting a viable first-pass triage role.",
    scores: { relevance: 5, credibility: 5, uniqueness: 4, actionability: 5 },
    storedAt: new Date("2026-05-28"),
  },
  /* Low-quality source to demonstrate score variation */
  {
    id: "src-9",
    projectId: "proj-2",
    subtopicIds: ["sub-2-2"],
    url: "https://medpharmainsider.com/ai-drug-discovery-2024",
    title: "AI Is Transforming Drug Discovery (Industry Blog)",
    fullText: "AI and machine learning are revolutionizing how pharmaceutical companies discover drugs...",
    tier: "industry",
    keyTakeaway: "Industry overview noting that 12 of the top 20 pharma companies now use generative AI for molecule design, though without quantitative performance benchmarks.",
    scores: { relevance: 3, credibility: 2, uniqueness: 2, actionability: 2 },
    storedAt: new Date("2026-05-29"),
  },
];

/* ─── Worker Activity ──────────────────────────────────────────────────────── */

export const WORKER_ACTIVITY: WorkerActivity[] = [
  { subtopicId: "sub-2-1", latestActivity: "Worker complete — 2 sources stored", sourcesStored: 2, status: "complete", whyNothingReport: null },
  { subtopicId: "sub-2-2", latestActivity: "Reading: scholar.google.com — evaluating relevance...", sourcesStored: 1, status: "running", whyNothingReport: null },
  { subtopicId: "sub-2-3", latestActivity: "Queued — waiting for worker slot", sourcesStored: 0, status: "queued", whyNothingReport: null },
  { subtopicId: "sub-2-4", latestActivity: "Queued — waiting for worker slot", sourcesStored: 0, status: "queued", whyNothingReport: null },
  { subtopicId: "sub-1-1", latestActivity: "Worker complete — 2 sources stored", sourcesStored: 2, status: "complete", whyNothingReport: null },
  { subtopicId: "sub-1-2", latestActivity: "Worker complete — 2 sources stored", sourcesStored: 2, status: "complete", whyNothingReport: null },
  { subtopicId: "sub-1-3", latestActivity: "Worker complete — 1 source stored", sourcesStored: 1, status: "complete", whyNothingReport: null },
  {
    subtopicId: "sub-1-4",
    latestActivity: "Worker complete — 1 source stored",
    sourcesStored: 1,
    status: "complete",
    whyNothingReport: null,
  },
];

/* ─── Chat Messages ────────────────────────────────────────────────────────── */

export const CHAT_MESSAGES: ChatMessage[] = [
  {
    id: "msg-1",
    projectId: "proj-1",
    role: "user",
    content: "What's the most cost-effective single intervention for a city with a limited budget?",
    citations: [],
    createdAt: new Date("2026-05-21T10:00:00"),
  },
  {
    id: "msg-2",
    projectId: "proj-1",
    role: "assistant",
    content: "Based on the sources in this project, **reflective roofing (cool roofs)** appears to be the most cost-effective single intervention for a budget-constrained city. Cool roofs can be applied incrementally through building permit requirements at little public cost, and installation runs $0.75–$3.00 per square foot. The EPA analysis in [src-1] documents ambient cooling of 1–5°F city-wide when adopted at scale, while the USDA's urban forestry work [src-4] notes tree canopy programs require sustained maintenance spending of ~$125/tree/year.\n\nIf the city has existing HUD CDBG-MIT eligibility, the funding mechanisms source [src-6] describes grants of $2M–$18M specifically for UHI interventions, which could fund a combination approach.",
    citations: [
      { sourceId: "src-1", sourceTitle: "Using Cool Roofs to Reduce Heat Islands — EPA", url: "https://www.epa.gov/heat-islands/using-cool-roofs-reduce-heat-islands" },
      { sourceId: "src-4", sourceTitle: "Urban Forestry Toolkit — USDA Forest Service", url: "https://treesforclimate.gov/urban-forestry-toolkit" },
      { sourceId: "src-6", sourceTitle: "HUD Community Development Block Grants for Climate Resilience", url: "https://www.hud.gov/program_offices/community_planning/climate" },
    ],
    createdAt: new Date("2026-05-21T10:01:30"),
  },
  {
    id: "msg-3",
    projectId: "proj-1",
    role: "user",
    content: "Do any studies look at combined interventions versus single strategies?",
    citations: [],
    createdAt: new Date("2026-05-21T10:03:00"),
  },
  {
    id: "msg-4",
    projectId: "proj-1",
    role: "assistant",
    content: "The green infrastructure study [src-5] is the most direct source on co-benefits — it quantifies both thermal and hydrological outcomes for green roofs together. For combined street-level interventions, the reflective pavement meta-analysis [src-2] notes that district-scale deployment (combining cool pavement, canopy, and green roofs) is necessary to achieve ambient cooling beyond 1°F. However, none of the stored sources include a head-to-head cost-effectiveness comparison of bundled vs. single-strategy implementations. This may be worth spawning a new research subtopic.",
    citations: [
      { sourceId: "src-5", sourceTitle: "Green roofs as thermal and hydrological co-benefit infrastructure", url: "https://doi.org/10.1016/j.landurbplan.2024.002" },
      { sourceId: "src-2", sourceTitle: "High-albedo pavements: meta-analysis of field studies 2015–2024", url: "https://doi.org/10.1016/j.enbuild.2024.001" },
    ],
    createdAt: new Date("2026-05-21T10:04:15"),
  },
];

/* ─── Reports ──────────────────────────────────────────────────────────────── */

export const REPORTS: Report[] = [
  {
    id: "rep-1",
    projectId: "proj-1",
    markdown: `# Urban Heat Island Mitigation Strategies for Mid-Sized American Cities

## Executive Summary

Urban heat islands (UHIs) elevate city temperatures 2–10°F above surrounding rural areas, increasing energy demand, heat-related illness, and air pollution. Three intervention categories show robust evidence for mid-sized cities: reflective surfaces, urban tree canopy expansion, and integrated green infrastructure. A phased combination approach—anchored by incremental cool-roof requirements and supplemented by targeted canopy investments—offers the best cost-benefit profile at the $5–20M budget range typical of mid-sized municipalities.

## 1. Reflective Surfaces

### Cool Roofs
Cool roofs are the most cost-effective single intervention. The EPA documents ambient temperature reductions of **1–5°F city-wide** when adoption reaches 50%+ of commercial and residential roof area [1]. Installation costs of **$0.75–$3.00 per square foot** are competitive with standard re-roofing, enabling mandate-at-permit approaches that require minimal public capital.

A 2024 meta-analysis of 47 field studies confirmed surface temperature reductions of up to 50°F on individual rooftops, with ambient effect scaling proportionally to adoption rate [2].

### Reflective Pavements
High-albedo street and parking surfaces reduce surface temperatures by **10–25°F**, though ambient cooling effect remains modest (0.2–1.0°F) unless deployed at district scale [2]. Best suited as a complement to cool roofs rather than a standalone strategy for budget-limited cities.

## 2. Urban Tree Canopy

Analysis of 38 mid-sized US cities found that **each 1% increase in canopy cover correlates with a 0.14°F reduction in mean summer temperature** [3]. Cities with 20–30% canopy cover reach the cost-effective threshold; below 15%, per-degree cooling costs rise steeply.

The USDA Forest Service recommends **30–40% canopy targets** for mid-sized cities and provides 15 climate-resilient species by hardiness zone. Ongoing maintenance averages **$125/tree/year**, making species selection for low-maintenance resilience a key planning variable [4].

## 3. Green Infrastructure Integration

Green roofs provide a **thermal + hydrological co-benefit** package: rooftop temperature reductions of 15–35°F and retention of 60–80% of precipitation events under 2 inches [5]. High installation costs ($10–25/sqft) require subsidy programs to reach meaningful scale.

Permeable paving offers moderate thermal benefit at lower cost than green roofs and can be phased into normal road resurfacing cycles.

## 4. Funding Mechanisms

HUD's CDBG-MIT program has funded 43 UHI mitigation projects totaling $380M since 2021, with individual grants of **$2M–$18M** available to qualifying municipalities in low-moderate income areas [6]. Cities without CDBG-MIT eligibility should evaluate:
- State climate resilience grant programs
- Green municipal bond issuance
- Public-private partnerships with utilities (who benefit from reduced peak demand)

## Recommended Strategy for Budget-Constrained Cities

1. **Year 1–2:** Enact cool-roof mandate for commercial re-roofing permits (near-zero public cost). Pilot reflective pavement on 2–3 high-traffic corridors.
2. **Year 2–4:** Apply for CDBG-MIT or equivalent grant. Use grant funding for targeted tree planting in high-heat-burden neighborhoods (equity lens).
3. **Year 4–7:** Expand canopy program and incorporate green infrastructure into stormwater capital projects (co-funding via separate stormwater utility).

## Sources

[1] EPA — Using Cool Roofs to Reduce Heat Islands
[2] High-albedo pavements meta-analysis, *Energy and Buildings* (2024)
[3] Urban tree canopy and heat mitigation, *Nature Climate Change* (2023)
[4] USDA Forest Service Urban Forestry Toolkit
[5] Green roofs as thermal and hydrological co-benefit infrastructure, *Landscape and Urban Planning* (2024)
[6] HUD Community Development Block Grants for Climate Resilience
`,
    sourceRefs: ["src-1", "src-2", "src-3", "src-4", "src-5", "src-6"],
    generatedAt: new Date("2026-05-21"),
  },
];

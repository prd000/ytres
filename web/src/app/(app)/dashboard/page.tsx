import { getProjects } from "@/lib/data/client";
import { DashboardView } from "@/components/features/dashboard/DashboardView";

export default async function DashboardPage() {
  const projects = await getProjects();
  return <DashboardView projects={projects} />;
}

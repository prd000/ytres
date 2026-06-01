import { PageContainer } from "@/components/layout/PageContainer";
import { NewProjectForm } from "@/components/features/project/NewProjectForm";

export default function NewProjectPage() {
  return (
    <div className="py-16">
      <PageContainer>
        <div className="max-w-2xl mx-auto">
          <h1 className="text-display-sm text-ink mb-2">New research project</h1>
          <p className="text-body-md text-muted mb-10">
            Describe what you want to research. ytres will generate a structured
            plan and gather sources.
          </p>
          <NewProjectForm />
        </div>
      </PageContainer>
    </div>
  );
}

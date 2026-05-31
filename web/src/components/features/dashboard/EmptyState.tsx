import Link from "next/link";
import { SpikeMark } from "@/components/ui/SpikeMark";

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-12 h-12 rounded-full bg-surface-card flex items-center justify-center mb-6">
        <SpikeMark size={20} className="text-muted" />
      </div>
      <h2 className="text-title-lg text-ink mb-2">No research projects yet</h2>
      <p className="text-body-md text-muted max-w-sm mb-8">
        Start your first project by submitting a research question. AI agents will handle the rest.
      </p>
      <Link
        href="/project/new"
        className="inline-flex items-center gap-2 h-10 px-5 text-button bg-primary text-on-primary rounded-md hover:bg-primary-active transition-colors"
      >
        Start researching
      </Link>
    </div>
  );
}

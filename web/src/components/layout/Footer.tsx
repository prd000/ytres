import Link from "next/link";
import { SpikeMark } from "@/components/ui/SpikeMark";
import { PageContainer } from "@/components/layout/PageContainer";

export function Footer() {
  return (
    <footer className="bg-surface-dark text-on-dark-soft mt-auto">
      <PageContainer className="py-16">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          <div className="flex items-center gap-2 text-on-dark">
            <SpikeMark size={12} className="text-on-dark" />
            <span className="text-title-sm tracking-tight">ytres</span>
          </div>

          <nav className="flex flex-wrap gap-x-8 gap-y-3 text-body-sm">
            <Link href="/dashboard" className="hover:text-on-dark transition-colors">
              Dashboard
            </Link>
            <Link href="/login" className="hover:text-on-dark transition-colors">
              Sign in
            </Link>
            <Link href="/signup" className="hover:text-on-dark transition-colors">
              Get started
            </Link>
          </nav>
        </div>

        <div className="mt-12 pt-6 border-t border-surface-dark-elevated text-body-sm">
          <p>© {new Date().getFullYear()} ytres. AI-powered research pipeline.</p>
        </div>
      </PageContainer>
    </footer>
  );
}

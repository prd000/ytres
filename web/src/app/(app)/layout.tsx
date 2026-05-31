import { ReactNode } from "react";
import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { getCurrentUser } from "@/lib/data/dal";
import { signOut } from "@/app/(auth)/actions";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();

  return (
    <div className="flex flex-col min-h-screen">
      <TopNav user={user} signOut={signOut} />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}

import { AuthShell } from "@/components/layout/AuthShell";
import { LoginForm } from "@/components/features/auth/LoginForm";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your research workspace"
    >
      <LoginForm initialError={error} />
    </AuthShell>
  );
}

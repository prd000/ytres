import { AuthShell } from "@/components/layout/AuthShell";
import { LoginForm } from "@/components/features/auth/LoginForm";

export default function LoginPage() {
  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your research workspace"
    >
      <LoginForm />
    </AuthShell>
  );
}

import { AuthShell } from "@/components/layout/AuthShell";
import { SignupForm } from "@/components/features/auth/SignupForm";

export default function SignupPage() {
  return (
    <AuthShell
      title="Create your account"
      subtitle="Start your first research project today"
    >
      <SignupForm />
    </AuthShell>
  );
}

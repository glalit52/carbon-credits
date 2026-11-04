import { Logo } from "@/components/logo";
import { Notice } from "@/components/ui";
import { DEMO } from "@/lib/env";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <div className="mb-8">
        <Logo />
      </div>
      <div className="w-full max-w-sm">
        {DEMO && (
          <div className="mb-4">
            <Notice tone="accent" title="Demo mode">
              Sign-in is switched off until Supabase is configured. <a className="underline" href="/app">Open the demo organisation</a> instead.
            </Notice>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

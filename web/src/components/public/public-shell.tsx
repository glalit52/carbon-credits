import Link from "next/link";

import { Logo } from "@/components/logo";

/** Frame for the pages anyone can open without an account. */
export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-3xl flex-col px-5">
      <header className="flex items-center justify-between py-5">
        <Logo />
        <Link href="/verify" className="text-sm font-medium text-brand">
          Verify a credit
        </Link>
      </header>
      <main className="flex-1 pb-16">{children}</main>
      <footer className="border-t border-border py-5 text-xs text-muted">
        This page shows registry facts only: who issued a credit, under which methodology, and whether it has been
        retired and for whom. No farmer or farm data is published.
      </footer>
    </div>
  );
}

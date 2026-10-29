import { LogOut } from "lucide-react";

import { Logo } from "@/components/logo";
import { MobileNav, NavLinks } from "@/components/shell/nav";
import { Badge, Select } from "@/components/ui";
import { signOut } from "@/lib/actions/auth";
import { switchOrganization } from "@/lib/actions/org";
import { getOrgContext } from "@/lib/data";
import { ROLE_LABEL } from "@/lib/roles";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const ctx = await getOrgContext();

  const orgSwitcher =
    ctx.orgs.length > 1 ? (
      <form action={switchOrganization} className="flex gap-2">
        <Select name="org_id" defaultValue={ctx.org.id} aria-label="Organisation" className="py-1.5">
          {ctx.orgs.map(({ org }) => (
            <option key={org.id} value={org.id}>
              {org.name}
            </option>
          ))}
        </Select>
        <button className="rounded-lg border border-border px-2 text-xs text-muted hover:bg-surface-2">Go</button>
      </form>
    ) : (
      <div className="truncate text-sm font-medium">{ctx.org.name}</div>
    );

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-6 border-r border-border bg-surface px-3 py-5 lg:flex">
        <div className="px-2">
          <Logo href="/app" />
        </div>
        <div className="px-2">{orgSwitcher}</div>
        <NavLinks />
        <div className="mt-auto px-2 text-xs text-muted">
          <div className="truncate font-medium text-text">{ctx.user.name ?? ctx.user.email}</div>
          <div className="flex items-center justify-between">
            <span>{ROLE_LABEL[ctx.role]}</span>
            <form action={signOut}>
              <button className="flex items-center gap-1 hover:text-text" title="Sign out">
                <LogOut className="h-3.5 w-3.5" /> Sign out
              </button>
            </form>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3 lg:hidden">
          <MobileNav>{orgSwitcher}</MobileNav>
          <Logo href="/app" />
        </header>
        {ctx.demo && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent-soft px-4 py-2 text-xs sm:px-8">
            <Badge tone="accent">Demo</Badge>
            <span>
              Read-only sample organisation, estimated by the real engine. Connect Supabase to sign up and save your
              own farms.
            </span>
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-8 sm:py-8">{children}</main>
      </div>
    </div>
  );
}

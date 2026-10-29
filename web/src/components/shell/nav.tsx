"use client";

import {
  Activity,
  BadgeCheck,
  FolderKanban,
  LayoutDashboard,
  Menu,
  Plug,
  Settings,
  Sprout,
  Upload,
  Users,
  Wallet,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { cx } from "@/components/ui";

const ITEMS = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/app/projects", label: "Projects", icon: FolderKanban },
  { href: "/app/farms", label: "Farms", icon: Sprout },
  { href: "/app/farmers", label: "Farmers", icon: Users },
  { href: "/app/import", label: "Import data", icon: Upload },
  { href: "/app/credits", label: "Credits", icon: BadgeCheck },
  { href: "/app/payments", label: "Payments", icon: Wallet },
  { href: "/app/integrations", label: "Integrations", icon: Plug },
  { href: "/app/activity", label: "Activity", icon: Activity },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {ITEMS.map(({ href, label, icon: Icon, exact }) => {
        const active = exact ? path === href : path === href || path.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cx(
              "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition",
              active ? "bg-brand-soft font-medium text-brand-strong" : "text-muted hover:bg-surface-2 hover:text-text",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function MobileNav({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="lg:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg p-2 text-muted hover:bg-surface-2"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="relative flex w-72 flex-col gap-4 bg-surface p-4 shadow-xl">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="self-end rounded-lg p-2 text-muted hover:bg-surface-2"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            {children}
            <NavLinks onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}

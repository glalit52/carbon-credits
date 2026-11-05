"use client";

import { Bell, KeyRound, Lock, Sliders, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/app/profile", label: "Profile & Identity", icon: User, exact: true },
  { href: "/app/profile/preferences", label: "Preferences & Units", icon: Sliders },
  { href: "/app/profile/security", label: "Security & 2FA", icon: Lock },
  { href: "/app/profile/api-keys", label: "Developer API Keys", icon: KeyRound },
  { href: "/app/profile/notifications", label: "Notifications", icon: Bell },
];

export function ProfileNav() {
  const pathname = usePathname();

  return (
    <div className="mb-6 flex overflow-x-auto border-b border-border text-sm">
      <div className="flex gap-2">
        {TABS.map(({ href, label, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2 border-b-2 px-4 py-2.5 font-medium transition whitespace-nowrap ${
                active
                  ? "border-brand text-brand font-semibold"
                  : "border-transparent text-muted hover:border-border hover:text-text"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}


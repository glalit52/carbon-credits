import Link from "next/link";

import { APP_NAME } from "@/lib/env";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 font-semibold tracking-tight">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-brand" />
        <path d="M9 21c0-6 4-10 13-11-1 8-5 12-11 12" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
        <path d="M9 23l6-6" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
      <span>{APP_NAME}</span>
    </Link>
  );
}

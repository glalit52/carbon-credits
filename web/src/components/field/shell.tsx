"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, useTransition } from "react";

import { setFieldLanguage } from "@/lib/actions/field";
import type { Language } from "@/lib/database.types";
import { LANGUAGES } from "@/lib/i18n";

export function LanguagePicker({ current }: { current: Language }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <select
      aria-label="Language"
      value={current}
      disabled={pending}
      onChange={(e) =>
        start(async () => {
          await setFieldLanguage(e.target.value as Language);
          router.refresh();
        })
      }
      className="rounded-lg border border-border bg-surface px-2 py-1 text-sm"
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.native}
        </option>
      ))}
    </select>
  );
}

/** Caches the field app so it opens with no signal. Production builds only. */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/field-sw.js", { scope: "/field" }).catch(() => {});
  }, []);
  return null;
}

function subscribe(cb: () => void) {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, () => navigator.onLine, () => true);
}

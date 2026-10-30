"use client";

import { CloudOff, RefreshCw, Trash2, Wifi } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Badge, Button, Card } from "@/components/ui";
import { submitFieldEnrolment } from "@/lib/actions/field";
import type { Language } from "@/lib/database.types";
import { type FieldDraft, queue, toFormData } from "@/lib/field-queue";
import { translator } from "@/lib/i18n";

import { useOnline } from "./shell";

/** Send every queued draft that has not been sent, one at a time. */
export async function sendQueued(onChange?: () => void): Promise<void> {
  for (const d of await queue.all()) {
    if (d.status === "sent" || d.status === "sending") continue;
    await queue.put({ ...d, status: "sending", error: undefined });
    onChange?.();
    let next: FieldDraft;
    try {
      const r = await submitFieldEnrolment(toFormData(d));
      next = r.ok
        ? { ...d, status: "sent", farm_id: r.farm_id, error: undefined }
        : { ...d, status: r.retry ? "queued" : "failed", error: r.error };
    } catch (e) {
      // No signal, or the server did not answer: stays queued for next time.
      next = { ...d, status: "queued", error: (e as Error).message };
    }
    await queue.put(next);
    onChange?.();
  }
}

export function QueueList({ lang }: { lang: Language }) {
  const t = translator(lang);
  const online = useOnline();
  const [drafts, setDrafts] = useState<FieldDraft[]>([]);
  const busy = useRef(false);

  const refresh = useCallback(async () => {
    setDrafts((await queue.all().catch(() => [])).sort((a, b) => b.created_at.localeCompare(a.created_at)));
  }, []);

  const sync = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      await sendQueued(refresh);
    } finally {
      busy.current = false;
    }
  }, [refresh]);

  useEffect(() => {
    // Subscribing to IndexedDB, an external store.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (online) void sync();
  }, [online, sync]);

  const waiting = drafts.filter((d) => d.status !== "sent");
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted">
          {t("field.queue")} {waiting.length > 0 && `(${waiting.length})`}
        </h2>
        <span className="flex items-center gap-1 text-xs text-muted">
          {online ? <Wifi className="h-3.5 w-3.5" /> : <CloudOff className="h-3.5 w-3.5" />}
          {online ? t("field.online") : t("field.offline")}
        </span>
      </div>
      {drafts.length === 0 ? (
        <p className="text-sm text-muted">{t("field.queue_empty")}</p>
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {drafts.map((d) => (
              <li key={d.id} className="flex items-start justify-between gap-3 px-4 py-3 text-sm">
                <div className="min-w-0">
                  <div className="font-medium">{d.farm.name}</div>
                  <div className="text-xs text-muted">
                    {d.farmer.name} · {new Date(d.created_at).toLocaleString()}
                  </div>
                  {d.error && d.status !== "sent" && <div className="mt-1 text-xs text-danger">{d.error}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge tone={d.status === "sent" ? "brand" : d.status === "failed" ? "danger" : "accent"}>
                    {d.status === "sent"
                      ? t("field.sent")
                      : d.status === "sending"
                        ? t("field.sending")
                        : d.status === "failed"
                          ? t("field.failed")
                          : t("field.queue")}
                  </Badge>
                  {(d.status === "sent" || d.status === "failed") && (
                    <button
                      type="button"
                      aria-label={t("field.discard")}
                      onClick={async () => {
                        await queue.remove(d.id);
                        void refresh();
                      }}
                      className="text-muted"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {waiting.length > 0 && (
            <div className="border-t border-border p-3">
              <Button type="button" variant="secondary" className="w-full" disabled={!online} onClick={() => void sync()}>
                <RefreshCw className="h-4 w-4" /> {t("field.sync_now")}
              </Button>
            </div>
          )}
        </Card>
      )}
    </section>
  );
}

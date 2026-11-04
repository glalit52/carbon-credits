"use client";

import { useEffect } from "react";

import { Button, ButtonLink, Card } from "@/components/ui";

/** Inside the app shell: the sidebar stays, so people can go elsewhere. */
export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  const digest = (error as { digest?: string } | null)?.digest;
  return (
    <Card className="mx-auto mt-10 max-w-lg p-8 text-center">
      <h1 className="text-lg font-semibold">Something went wrong loading this page</h1>
      <p className="mt-2 text-sm text-muted">
        Nothing you entered was lost unless you saw a message saying it was saved. Try again; if it keeps happening,
        send this reference to your admin.
      </p>
      {digest && <code className="mt-3 inline-block rounded bg-surface-2 px-2 py-1 text-xs">{digest}</code>}
      <div className="mt-6 flex justify-center gap-2">
        <Button onClick={() => retry()}>Try again</Button>
        <ButtonLink href="/app" variant="secondary">
          Back to overview
        </ButtonLink>
      </div>
    </Card>
  );
}

"use client";

import { useActionState, type ReactNode } from "react";

import type { ActionResult } from "@/lib/actions/result";

import { Button, Notice, cx } from "./ui";

/**
 * A form bound to a server action, showing its error or confirmation. The
 * action does the real validation; this only renders what it says.
 */
export function ActionForm({
  action,
  submit,
  children,
  className,
  submitClassName,
  variant = "primary",
  hidden,
}: {
  action: (prev: ActionResult, form: FormData) => Promise<ActionResult>;
  submit: ReactNode;
  children?: ReactNode;
  className?: string;
  submitClassName?: string;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  hidden?: Record<string, string | undefined>;
}) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className={cx("flex flex-col gap-4", className)}>
      {hidden &&
        Object.entries(hidden).map(([k, v]) => (v === undefined ? null : <input key={k} type="hidden" name={k} value={v} />))}
      {children}
      {state.error && <Notice tone="danger">{state.error}</Notice>}
      {state.message && <Notice tone="brand">{state.message}</Notice>}
      <Button type="submit" variant={variant} disabled={pending} className={submitClassName}>
        {pending ? "Working…" : submit}
      </Button>
    </form>
  );
}

"use client";

import { useActionState } from "react";

import type { Role } from "@/lib/database.types";
import { changeRole } from "@/lib/actions/org";
import { ROLE_LABEL } from "@/lib/roles";

import { Select } from "./ui";

const ROLES: Role[] = ["owner", "admin", "reviewer", "analyst", "field_agent", "viewer"];

/** A role picker that saves on change and says why when it cannot. */
export function MemberRole({ userId, role, disabled }: { userId: string; role: Role; disabled?: boolean }) {
  const [state, action, pending] = useActionState(changeRole, {});
  return (
    <form action={action} className="flex flex-col gap-1">
      <input type="hidden" name="user_id" value={userId} />
      <Select
        name="role"
        defaultValue={role}
        disabled={disabled || pending}
        onChange={(e) => e.currentTarget.form?.requestSubmit()}
        className="w-40 py-1.5"
        aria-label="Role"
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r]}
          </option>
        ))}
      </Select>
      {state.error && <span className="text-xs text-danger">{state.error}</span>}
    </form>
  );
}

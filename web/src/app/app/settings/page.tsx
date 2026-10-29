import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { MemberRole } from "@/components/member-role";
import { Badge, Card, CardHeader, Field, Input, PageHeader, Select, Table, Td, Th } from "@/components/ui";
import { updatePassword } from "@/lib/actions/auth";
import { inviteMember, removeMember, revokeInvitation, updateOrganization } from "@/lib/actions/org";
import { getOrgContext, listInvitations, listMembers } from "@/lib/data";
import { fmt } from "@/lib/format";
import { can, INVITABLE, ROLE_HELP, ROLE_LABEL } from "@/lib/roles";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const ctx = await getOrgContext();
  const admin = can.administer(ctx.role);
  const [members, invitations] = await Promise.all([
    listMembers(ctx.org.id),
    admin ? listInvitations(ctx.org.id) : Promise.resolve([]),
  ]);

  return (
    <>
      <PageHeader title="Settings" description="Your organisation, the people in it and what each of them can do." />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Members" description={`${members.length} people in ${ctx.org.name}`} />
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Role</Th>
                <Th>Joined</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.user_id}>
                  <Td>
                    <div className="font-medium">{m.full_name ?? "Unnamed member"}</div>
                    {m.user_id === ctx.user.id && <Badge tone="brand">You</Badge>}
                  </Td>
                  <Td>
                    {admin && m.user_id !== ctx.user.id ? (
                      <MemberRole userId={m.user_id} role={m.role} disabled={ctx.demo} />
                    ) : (
                      ROLE_LABEL[m.role]
                    )}
                  </Td>
                  <Td className="text-muted">{fmt.date(m.created_at)}</Td>
                  <Td className="text-right">
                    {admin && m.user_id !== ctx.user.id && m.role !== "owner" && (
                      <form action={removeMember}>
                        <input type="hidden" name="user_id" value={m.user_id} />
                        <button className="text-xs text-danger hover:underline" disabled={ctx.demo}>
                          Remove
                        </button>
                      </form>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card>
          <CardHeader title="What each role can do" />
          <dl className="space-y-3 p-5 text-sm">
            {Object.entries(ROLE_HELP).map(([role, help]) => (
              <div key={role}>
                <dt className="font-medium">{ROLE_LABEL[role as keyof typeof ROLE_LABEL]}</dt>
                <dd className="text-muted">{help}</dd>
              </div>
            ))}
          </dl>
        </Card>

        {admin && (
          <Card className="lg:col-span-2">
            <CardHeader
              title="Invite someone"
              description="They get a link to sign up or sign in with this email address, and join with this role."
            />
            <div className="p-5">
              <ActionForm action={inviteMember} submit="Create invitation link" className="sm:max-w-md">
                <Field label="Email">
                  <Input name="email" type="email" required placeholder="agent@example.org" />
                </Field>
                <Field label="Role">
                  <Select name="role" defaultValue="field_agent">
                    {INVITABLE.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]} — {ROLE_HELP[r]}
                      </option>
                    ))}
                  </Select>
                </Field>
              </ActionForm>
              {invitations.length > 0 && (
                <div className="mt-6">
                  <h3 className="mb-2 text-sm font-semibold">Pending invitations</h3>
                  <ul className="divide-y divide-border rounded-lg border border-border text-sm">
                    {invitations.map((inv) => (
                      <li key={inv.id} className="flex items-center justify-between gap-3 px-3 py-2">
                        <span>
                          {inv.email} · {ROLE_LABEL[inv.role]}
                          <span className="ml-2 text-xs text-muted">expires {fmt.date(inv.expires_at)}</span>
                        </span>
                        <form action={revokeInvitation}>
                          <input type="hidden" name="id" value={inv.id} />
                          <button className="text-xs text-danger hover:underline" disabled={ctx.demo}>
                            Revoke
                          </button>
                        </form>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Card>
        )}

        <div className="flex flex-col gap-6">
          {admin && (
            <Card>
              <CardHeader title="Organisation" />
              <div className="p-5">
                <ActionForm action={updateOrganization} submit="Save" variant="secondary">
                  <Field label="Name">
                    <Input name="name" defaultValue={ctx.org.name} required />
                  </Field>
                  <Field label="Country">
                    <Input name="country" defaultValue={ctx.org.country ?? ""} />
                  </Field>
                </ActionForm>
              </div>
            </Card>
          )}
          <Card>
            <CardHeader title="Your account" description={ctx.user.email ?? undefined} />
            <div className="p-5">
              <ActionForm action={updatePassword} submit="Change password" variant="secondary">
                <Field label="New password" hint="At least 10 characters.">
                  <Input name="password" type="password" autoComplete="new-password" minLength={10} />
                </Field>
              </ActionForm>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

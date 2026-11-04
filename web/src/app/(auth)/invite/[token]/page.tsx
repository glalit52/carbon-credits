import type { Metadata } from "next";

import { ActionForm } from "@/components/action-form";
import { ButtonLink, Card } from "@/components/ui";
import { acceptInvitation } from "@/lib/actions/org";
import { getUser } from "@/lib/data";

export const metadata: Metadata = { title: "Join an organisation" };

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const user = await getUser();
  const here = `/invite/${token}`;
  return (
    <Card className="p-6">
      <h1 className="text-lg font-semibold">You&apos;ve been invited</h1>
      {user ? (
        <>
          <p className="mt-1 text-sm text-muted">
            Signed in as <strong>{user.email}</strong>. The invitation must have been sent to this address.
          </p>
          <ActionForm action={acceptInvitation} submit="Accept and join" className="mt-5" hidden={{ token }} />
        </>
      ) : (
        <>
          <p className="mt-1 text-sm text-muted">Sign in or create an account with the email the invitation was sent to.</p>
          <div className="mt-5 flex flex-col gap-2">
            <ButtonLink href={`/signup?next=${encodeURIComponent(here)}`}>Create an account</ButtonLink>
            <ButtonLink href={`/login?next=${encodeURIComponent(here)}`} variant="secondary">
              Sign in
            </ButtonLink>
          </div>
        </>
      )}
    </Card>
  );
}

import { ButtonLink, Card } from "@/components/ui";

export default function AppNotFound() {
  return (
    <Card className="mx-auto mt-10 max-w-lg p-8 text-center">
      <h1 className="text-lg font-semibold">Not found in this organisation</h1>
      <p className="mt-2 text-sm text-muted">
        It may have been deleted, or it belongs to another organisation you are a member of. Switch organisation from
        the sidebar if so.
      </p>
      <ButtonLink href="/app" className="mt-6">
        Back to overview
      </ButtonLink>
    </Card>
  );
}

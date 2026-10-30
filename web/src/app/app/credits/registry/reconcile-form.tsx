"use client";

import { useActionState } from "react";

import { Badge, Button, Card, CardHeader, Field, Input, Notice, Select, Stat, Table, Td, Th } from "@/components/ui";
import { reconcileRegistry, type ReconcileState } from "@/lib/actions/registry";

export function ReconcileForm({ projects }: { projects: { id: string; name: string }[] }) {
  const [state, action, pending] = useActionState<ReconcileState, FormData>(reconcileRegistry, {});
  const r = state.result;
  const label = (id: string) => state.labels?.[id] ?? id.slice(0, 8);
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader
          title="Upload the registry's export"
          description="Verra, Gold Standard, Puro and Isometric exports are matched by column name, whatever their order."
        />
        <form action={action} className="grid gap-4 p-5 sm:grid-cols-4">
          <Field label="Registry">
            <Select name="registry" defaultValue="Verra">
              <option>Verra</option>
              <option>Gold Standard</option>
              <option>Puro.earth</option>
              <option>Isometric</option>
            </Select>
          </Field>
          <Field label="Project">
            <Select name="project_id" defaultValue="">
              <option value="">All projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Export (CSV)">
            <Input name="file" type="file" accept=".csv,text/csv" required />
          </Field>
          <div className="flex items-end">
            <Button type="submit" disabled={pending} className="w-full">
              {pending ? "Reconciling…" : "Reconcile"}
            </Button>
          </div>
        </form>
        {state.error && (
          <div className="px-5 pb-5">
            <Notice tone="danger">{state.error}</Notice>
          </div>
        )}
      </Card>

      {r && (
        <>
          <Notice tone={r.clean ? "brand" : "accent"} title={r.clean ? "The ledgers agree" : "The ledgers disagree"}>
            {r.clean
              ? `Every issued vintage is in the ${r.registry} export with the same quantity, and the export holds nothing we did not issue.`
              : `${r.findings.length} finding${r.findings.length === 1 ? "" : "s"} below. Until they are resolved, someone may have sold, retired or cancelled credits the other side does not know about.`}
          </Notice>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Registry rows" value={r.rows} />
            <Stat label="Matched" value={r.matched} tone="brand" />
            <Stat label="Quantity disagreements" value={r.disagreements} tone={r.disagreements ? "danger" : undefined} />
            <Stat label="Retired at registry" value={`${r.retired_t} t`} hint={r.cancelled_t ? `${r.cancelled_t} t cancelled` : undefined} />
          </div>
          {r.findings.length > 0 && (
            <Card>
              <CardHeader title="Findings" />
              <ul className="space-y-2 p-5 text-sm">
                {r.findings.map((f) => (
                  <li key={f}>{Object.entries(state.labels ?? {}).reduce((s, [id, l]) => s.replaceAll(id, l), f)}</li>
                ))}
              </ul>
            </Card>
          )}
          <Card>
            <CardHeader title="Matches" description="Serial block first, then the registry reference, then vintage and quantity." />
            <Table>
              <thead>
                <tr>
                  <Th>Our vintage</Th>
                  <Th>Registry line</Th>
                  <Th>Matched on</Th>
                  <Th className="text-right">Ours</Th>
                  <Th className="text-right">Theirs</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {r.matches.map((m) => (
                  <tr key={m.issuance_id}>
                    <Td>{label(m.issuance_id)}</Td>
                    <Td className="tabular">{m.registry_line}</Td>
                    <Td>
                      <Badge tone={m.basis === "vintage+quantity" ? "accent" : "info"}>{m.basis}</Badge>
                    </Td>
                    <Td className="tabular text-right">{m.ours}</Td>
                    <Td className="tabular text-right">{m.theirs}</Td>
                    <Td>{m.agrees ? <Badge tone="brand">agrees</Badge> : <Badge tone="danger">differs</Badge>}</Td>
                  </tr>
                ))}
                {r.missing_at_registry.map((id) => (
                  <tr key={id}>
                    <Td>{label(id)}</Td>
                    <Td colSpan={4} className="text-muted">
                      not in the export
                    </Td>
                    <Td>
                      <Badge tone="danger">missing</Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <p className="px-5 py-3 text-xs text-muted">
              Columns used: {Object.entries(r.columns).map(([k, v]) => `${k} ← “${v}”`).join(", ")}
              {r.ignored_columns.length ? `. Ignored: ${r.ignored_columns.join(", ")}` : ""}.
            </p>
          </Card>
          {r.unknown_rows.length > 0 && (
            <Card>
              <CardHeader title="At the registry, not in our ledger" />
              <Table>
                <thead>
                  <tr>
                    <Th>Line</Th>
                    <Th>Vintage</Th>
                    <Th className="text-right">Quantity</Th>
                    <Th>Serial</Th>
                    <Th>Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {r.unknown_rows.map((u) => (
                    <tr key={u.line}>
                      <Td className="tabular">{u.line}</Td>
                      <Td>{u.vintage ?? "—"}</Td>
                      <Td className="tabular text-right">{u.quantity}</Td>
                      <Td className="text-xs">{u.serial || "—"}</Td>
                      <Td>{u.status || "—"}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

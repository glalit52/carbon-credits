"use client";

import { Download, FileUp } from "lucide-react";
import { useMemo, useState, useTransition } from "react";

import type { Project } from "@/lib/database.types";
import { commitImport } from "@/lib/actions/imports";
import { parseBoundaryFile } from "@/lib/geo";
import {
  type ImportKind,
  type ImportPreview,
  previewFarmFeatures,
  previewFarms,
  previewPractices,
  previewSoil,
  TEMPLATES,
  templateCsv,
} from "@/lib/import";

import { FarmMap } from "./map/farm-map";
import { Badge, Button, Card, CardHeader, Field, Notice, Select, Table, Td, Th, cx } from "./ui";

const KINDS: { id: ImportKind; label: string; accepts: string }[] = [
  { id: "farms", label: "Farms and farmers", accepts: ".csv,.kml,.geojson,.json,.wkt" },
  { id: "practices", label: "Practice records", accepts: ".csv" },
  { id: "soil", label: "Soil lab results", accepts: ".csv" },
];

function preview(kind: ImportKind, text: string, filename: string): ImportPreview<unknown> {
  if (kind === "farms") {
    if (/\.(kml|geojson|json|wkt)$/i.test(filename) || /^\s*[{<]/.test(text)) {
      return previewFarmFeatures(parseBoundaryFile(text, filename));
    }
    return previewFarms(text);
  }
  return kind === "practices" ? previewPractices(text) : previewSoil(text);
}

function download(kind: ImportKind) {
  const blob = new Blob([templateCsv(kind)], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${kind}-template.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function Importer({ projects, readOnly }: { projects: Project[]; readOnly: boolean }) {
  const [kind, setKind] = useState<ImportKind>("farms");
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [outcome, setOutcome] = useState<{ error?: string; message?: string } | null>(null);
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [pending, start] = useTransition();

  const { result, parseError } = useMemo(() => {
    if (!file) return { result: null, parseError: null };
    try {
      return { result: preview(kind, file.text, file.name), parseError: null };
    } catch (e) {
      return { result: null, parseError: (e as Error).message };
    }
  }, [kind, file]);

  const farmsOnMap = useMemo(
    () =>
      kind === "farms" && result
        ? result.results
            .filter((r) => r.value)
            .slice(0, 2000)
            .map((r, i) => {
              const v = r.value as { name: string; boundary: never; area_ha: number; status: string };
              return { id: String(i), name: v.name, boundary: v.boundary, status: v.status, area_ha: v.area_ha };
            })
        : [],
    [kind, result],
  );

  const rows = result?.results.filter((r) => !onlyProblems || r.errors.length || r.warnings.length) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader title="1. What are you importing?" />
        <div className="grid gap-3 p-5 sm:grid-cols-3">
          {KINDS.map((k) => (
            <button
              key={k.id}
              type="button"
              onClick={() => {
                setKind(k.id);
                setOutcome(null);
              }}
              className={cx(
                "rounded-lg border px-4 py-3 text-left text-sm transition",
                kind === k.id ? "border-brand bg-brand-soft" : "border-border hover:bg-surface-2",
              )}
            >
              <div className="font-medium">{k.label}</div>
              <div className="text-xs text-muted">{k.accepts.replaceAll(",", " ")}</div>
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-3 border-t border-border p-5 text-sm sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-2xl text-muted">{TEMPLATES[kind].help}</p>
          <Button type="button" variant="secondary" onClick={() => download(kind)}>
            <Download className="h-4 w-4" /> Template
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title="2. Choose the file" description="Nothing is saved until you confirm below." />
        <div className="flex flex-col gap-4 p-5">
          <label className="flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm hover:bg-surface-2">
            <FileUp className="h-6 w-6 text-muted" />
            <span className="font-medium">{file ? file.name : "Choose a file"}</span>
            <span className="text-xs text-muted">Columns are matched by name; common spellings such as “Latitude” or “Plot ID” work.</span>
            <input
              type="file"
              accept={KINDS.find((k) => k.id === kind)!.accepts}
              className="sr-only"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setOutcome(null);
                setFile({ name: f.name, text: await f.text() });
              }}
            />
          </label>
          {kind === "farms" && (
            <Field label="Add the farms to" className="sm:max-w-sm">
              <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">No project yet</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {parseError && <Notice tone="danger">{parseError}</Notice>}
        </div>
      </Card>

      {result && (
        <Card>
          <CardHeader
            title="3. Check and import"
            description={`${result.results.length} rows read`}
            action={
              <label className="flex items-center gap-2 text-xs text-muted">
                <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
                Only rows with problems
              </label>
            }
          />
          <div className="flex flex-wrap gap-2 px-5 pt-4">
            <Badge tone="brand">{result.ok} ready</Badge>
            {result.warned > 0 && <Badge tone="accent">{result.warned} with warnings</Badge>}
            {result.failed > 0 && <Badge tone="danger">{result.failed} will be skipped</Badge>}
          </div>
          {farmsOnMap.length > 0 && (
            <div className="px-5 pt-4">
              <FarmMap farms={farmsOnMap} linkBase={null} className="h-72" />
            </div>
          )}
          <Table className="mt-4 max-h-[480px] overflow-y-auto">
            <thead>
              <tr>
                <Th>Row</Th>
                <Th>Record</Th>
                <Th>Problems</Th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 500).map((r) => {
                const v = r.value as Record<string, unknown> | undefined;
                return (
                  <tr key={r.row}>
                    <Td className="tabular text-muted">{r.row}</Td>
                    <Td>
                      {v ? (
                        <span>
                          <span className="font-medium">{String(v.name ?? v.farm_ref ?? "")}</span>
                          {typeof v.area_ha === "number" && <span className="text-muted"> · {v.area_ha.toFixed(2)} ha</span>}
                          {v.status === "draft" && <Badge tone="accent" className="ml-2">draft</Badge>}
                        </span>
                      ) : (
                        <Badge tone="danger">skipped</Badge>
                      )}
                    </Td>
                    <Td className="text-xs">
                      {r.errors.map((e) => (
                        <div key={e} className="text-danger">
                          {e}
                        </div>
                      ))}
                      {r.warnings.map((w) => (
                        <div key={w} className="text-accent">
                          {w}
                        </div>
                      ))}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
          {rows.length > 500 && <p className="px-5 pt-2 text-xs text-muted">Showing the first 500 rows.</p>}
          <div className="flex flex-col gap-3 p-5">
            {outcome?.error && <Notice tone="danger">{outcome.error}</Notice>}
            {outcome?.message && <Notice tone="brand">{outcome.message}</Notice>}
            <Button
              type="button"
              disabled={pending || result.ok === 0 || readOnly}
              onClick={() =>
                start(async () => {
                  setOutcome(await commitImport({ kind, text: file!.text, filename: file!.name, projectId }));
                })
              }
              className="self-start"
            >
              {pending ? "Importing…" : `Import ${result.ok} ${result.ok === 1 ? "row" : "rows"}`}
            </Button>
            {readOnly && <p className="text-xs text-muted">The demo is read-only: preview works, importing does not.</p>}
          </div>
        </Card>
      )}
    </div>
  );
}

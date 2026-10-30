import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/action-form";
import {
  CanopySeries,
  LoggerLevels,
  NdviSeries,
  RadarSeries,
  SceneTimeline,
} from "@/components/monitoring-charts";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Notice,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { uploadLogger } from "@/lib/actions/monitoring";
import { getFarm, getOrgContext, getProject, listEstimates, listSensorUploads } from "@/lib/data";
import {
  EngineError,
  type EngineResult,
  type LoggerResult,
  type Monitoring,
  runScenes,
  type SceneCoverage,
} from "@/lib/engine";
import { DEMO, engineConfig } from "@/lib/env";
import { fmt } from "@/lib/format";
import { can } from "@/lib/roles";

export const metadata: Metadata = { title: "Monitoring" };

type Search = { season?: string; sensor?: string; from?: string; to?: string; scenes?: string };

/** Last day of the window, as YYYY-MM-DD, in UTC. */
const isoDay = (d: Date) => d.toISOString().slice(0, 10);

export default async function MonitoringPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const [{ id }, q] = await Promise.all([params, searchParams]);
  const ctx = await getOrgContext();
  const farm = await getFarm(ctx.org.id, id);
  if (!farm) notFound();
  const [project, estimates, uploads] = await Promise.all([
    farm.project_id ? getProject(ctx.org.id, farm.project_id) : null,
    listEstimates(ctx.org.id, farm.id),
    listSensorUploads(ctx.org.id, farm.id),
  ]);
  // The series lives on the latest year's row of each run.
  const monitoring: Monitoring | undefined = estimates
    .map((e) => (e.result as unknown as EngineResult).monitoring)
    .filter((m): m is Monitoring => !!m)
    .at(-1);
  const rice = project?.pathway === "rice";

  const regimes = monitoring?.regimes ?? [];
  const seasonKey = (r: { year: number; season: string }) => `${r.year}-${r.season}`;
  const regime = regimes.find((r) => seasonKey(r) === q.season) ?? regimes.at(-1);
  const calls = (monitoring?.radar ?? []).filter(
    (c) => regime && c.season === regime.season && c.day >= regime.start && c.day <= regime.end,
  );
  const optical = (monitoring?.optical ?? []).filter((o) =>
    regime ? o.day >= regime.start && o.day <= regime.end : true,
  );

  // Scene catalogue: only when asked, since it is a live query.
  const today = new Date();
  const to = q.to ?? isoDay(today);
  const from = q.from ?? isoDay(new Date(today.getTime() - 180 * 86_400_000));
  const sensor = q.sensor === "s2" ? "s2" : "s1";
  let coverage: SceneCoverage | null = null;
  let sceneProblem: string | null = null;
  if (q.scenes) {
    if (!engineConfig()) {
      sceneProblem = DEMO
        ? "The scene catalogue is a live query through the engine; the demo has no engine connected."
        : "Connect the engine (CARBONSTACK_ENGINE_URL and CARBONSTACK_ENGINE_TOKEN) to query the scene catalogue.";
    } else {
      try {
        coverage = await runScenes({ boundary: farm.boundary, start: from, end: to, sensor });
      } catch (e) {
        sceneProblem = e instanceof EngineError ? e.message : (e as Error).message;
      }
    }
  }

  const upload = uploads[0];
  const logger = upload?.summary as unknown as LoggerResult | undefined;

  return (
    <>
      <PageHeader
        crumbs={[
          { href: "/app/farms", label: "Farms" },
          { href: `/app/farms/${farm.id}`, label: farm.name },
        ]}
        title="Monitoring"
        description={
          rice
            ? "Was the field actually dry? Radar sees through monsoon cloud; field loggers check the radar."
            : "Is the canopy growing as the estimate assumes?"
        }
      />

      {monitoring?.simulated && (
        <div className="mb-6">
          <Notice tone="accent" title="Simulated observations">
            These series are simulated from this farm&apos;s own climate and crop calendar
            {rice ? ", and the radar calls come from the same detector real Sentinel-1 granules will go through" : ""}.
            They show what the estimate was built from; they are not satellite measurements of this field yet.
          </Notice>
        </div>
      )}

      {!monitoring ? (
        <Card>
          <EmptyState
            title="No monitoring series yet"
            body="Run this farm's estimate; each run now keeps the series it was built from."
          />
        </Card>
      ) : rice ? (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="Water regime by season"
              description="Adoption confidence multiplies the creditable area. It rewards seasons the radar saw often and dry-downs it saw clearly."
              action={
                <form className="flex items-center gap-2">
                  <Select
                    name="season"
                    defaultValue={regime ? seasonKey(regime) : undefined}
                    aria-label="Season"
                    className="min-w-36"
                  >
                    {regimes.map((r) => (
                      <option key={seasonKey(r)} value={seasonKey(r)}>
                        {r.season} {r.year}
                      </option>
                    ))}
                  </Select>
                  <Button type="submit" variant="secondary">
                    Show
                  </Button>
                </form>
              }
            />
            {regime ? (
              <div className="p-5">
                <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Stat label="Adoption confidence" value={fmt.pct(regime.adoption_confidence)} tone="brand" />
                  <Stat
                    label="AWD dry-downs"
                    value={`${regime.qualifying_spells} of 3`}
                    hint="counted toward the target"
                  />
                  <Stat
                    label="Passes readable"
                    value={`${regime.usable_passes} / ${regime.passes}`}
                    hint={`${fmt.pct(regime.coverage)} coverage`}
                  />
                  <Stat label="Called drained" value={fmt.pct(regime.drained_fraction)} hint="of readable passes" />
                </div>
                <RadarSeries calls={calls} spells={regime.spells} />
                <p className="mt-2 text-xs text-muted">
                  Each mark is one Sentinel-1 pass, normalised to 38° incidence. Shaded bands are dry spells; the
                  grey band at the end is the harvest drain, which the baseline field does too and is not credited.
                  Around mid-season a flooded and a drained field return the same signal, and the detector says
                  &ldquo;not separable&rdquo; rather than guessing.
                </p>
                {regime.warnings.length > 0 && (
                  <ul className="mt-4 space-y-1 text-sm">
                    {regime.warnings.map((w) => (
                      <li key={w} className="text-muted">
                        • {w}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <EmptyState title="No closed season in the series" />
            )}
          </Card>

          {regime && regime.spells.length > 0 && (
            <Card>
              <CardHeader title="Dry spells this season" />
              <Table>
                <thead>
                  <tr>
                    <Th>From</Th>
                    <Th>To</Th>
                    <Th className="text-right">Days</Th>
                    <Th className="text-right">Passes</Th>
                    <Th className="text-right">Confidence</Th>
                    <Th>Counted</Th>
                  </tr>
                </thead>
                <tbody>
                  {regime.spells.map((s) => {
                    const counted = !s.terminal && s.days >= 6 && (s.passes >= 2 || s.mean_confidence >= 0.8);
                    return (
                      <tr key={s.start}>
                        <Td>{fmt.date(s.start)}</Td>
                        <Td>{fmt.date(s.end)}</Td>
                        <Td className="tabular text-right">{s.days}</Td>
                        <Td className="tabular text-right">{s.passes}</Td>
                        <Td className="tabular text-right">{fmt.pct(s.mean_confidence)}</Td>
                        <Td>
                          {s.terminal ? (
                            <Badge>harvest drain</Badge>
                          ) : counted ? (
                            <Badge tone="brand">AWD event</Badge>
                          ) : (
                            <Badge tone="accent">too short or unclear</Badge>
                          )}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </Card>
          )}

          <Card>
            <CardHeader title="Optical" description="Sentinel-2 greenness and surface water. Gaps are passes lost to cloud." />
            <div className="p-5">
              <NdviSeries readings={optical} water />
            </div>
          </Card>
        </div>
      ) : (
        <Card>
          <CardHeader title="Canopy" description="Height and its retrieval error; short canopies are the least certain." />
          <div className="p-5">
            <CanopySeries readings={monitoring.optical} />
          </div>
          <div className="border-t border-border p-5">
            <NdviSeries readings={monitoring.optical} water={false} />
          </div>
        </Card>
      )}

      {rice && (
        <Card className="mt-6">
          <CardHeader
            title="Field water loggers"
            description="A logger in an AWD field tube is the ground truth the radar is scored against. Upload its export: device_id, plot_id, timestamp, water_level_cm."
          />
          {logger ? (
            <div className="p-5">
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-medium">
                  {upload.file_name}{" "}
                  <span className="font-normal text-muted">
                    · {fmt.date(upload.first_day)} – {fmt.date(upload.last_day)} · {upload.readings.toLocaleString()} readings
                  </span>
                </p>
                {upload.file_path && (
                  <Link href={`/app/evidence?path=${encodeURIComponent(upload.file_path)}`} className="text-sm text-brand underline">
                    Original file
                  </Link>
                )}
              </div>
              <LoggerLevels
                days={logger.days.filter((d) => d.device_id === logger.records[0]?.device_id)}
                thresholds={logger.thresholds} calls={monitoring?.radar} />
              <p className="mt-2 text-xs text-muted">
                {logger.records.length > 1 && `Showing ${logger.records[0].device_id}; the summary below covers all ${logger.records.length} loggers. `}
                Dotted verticals are radar passes. A dry-down counts when the water table reaches{" "}
                {Math.abs(logger.thresholds.safe_awd_cm)} cm below the surface, the IRRI safe-AWD depth.
              </p>

              <div className="mt-5 grid gap-6 lg:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Measured dry-downs</h3>
                  {logger.records.flatMap((r) => r.dry_downs).length ? (
                    <ul className="space-y-1 text-sm">
                      {logger.records.flatMap((r) =>
                        r.dry_downs.map((d) => (
                          <li key={`${r.device_id}-${d.from}`}>
                            {fmt.date(d.from)} – {fmt.date(d.to)}{" "}
                            <span className="text-muted">
                              ({r.device_id}, down to {d.deepest_cm} cm)
                            </span>
                          </li>
                        )),
                      )}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted">None reached the safe-AWD depth.</p>
                  )}
                  {logger.records.some((r) => r.issues.length || r.dropped_spikes) && (
                    <>
                      <h3 className="mb-2 mt-4 text-sm font-semibold">Cleaning</h3>
                      <ul className="space-y-1 text-sm text-muted">
                        {logger.records.map((r) => (
                          <li key={r.device_id}>
                            {r.device_id}: {r.dropped_spikes} spike{r.dropped_spikes === 1 ? "" : "s"} dropped
                            {r.issues.length ? `; ${r.issues.join("; ")}` : ""}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {logger.other_plots.length > 0 && (
                    <p className="mt-3 text-xs text-muted">
                      The file also held {logger.other_plots.length} other plot(s), left out here.
                    </p>
                  )}
                </div>
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Radar against the logger</h3>
                  {logger.validation ? (
                    <>
                      <Table className="[&_table]:min-w-0">
                        <thead>
                          <tr>
                            <Th />
                            <Th className="text-right">Logger: flooded</Th>
                            <Th className="text-right">Logger: drained</Th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <Td>Radar: flooded</Td>
                            <Td className="tabular text-right">{logger.validation.true_positive}</Td>
                            <Td className="tabular text-right">{logger.validation.false_positive}</Td>
                          </tr>
                          <tr>
                            <Td>Radar: drained</Td>
                            <Td className="tabular text-right font-medium text-danger">
                              {logger.validation.false_negative}
                            </Td>
                            <Td className="tabular text-right">{logger.validation.true_negative}</Td>
                          </tr>
                        </tbody>
                      </Table>
                      <p className="mt-2 text-sm">
                        {fmt.pct(logger.validation.accuracy)} of {logger.validation.called} called passes agree;{" "}
                        {logger.validation.abstained} not separable.{" "}
                        <strong>{logger.validation.over_credit_errors}</strong> over-credit error
                        {logger.validation.over_credit_errors === 1 ? "" : "s"} (radar said drained, water was standing).
                      </p>
                      {!logger.validation.sufficient && (
                        <p className="mt-1 text-xs text-muted">
                          {logger.validation.matched_passes} matched passes; 30 are needed before the accuracy means
                          much.
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-sm text-muted">
                      No radar passes fall inside the logger&apos;s record. Run the estimate to refresh the series.
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <EmptyState title="No logger files yet" />
          )}
          {can.enrol(ctx.role) && (
            <div className="border-t border-border p-5">
              <ActionForm action={uploadLogger} submit="Upload and check" hidden={{ farm_id: farm.id }} className="max-w-md">
                <Field label="Logger export (CSV)">
                  <Input name="file" type="file" accept=".csv,text/csv" required />
                </Field>
              </ActionForm>
            </div>
          )}
          {uploads.length > 1 && (
            <p className="border-t border-border px-5 py-3 text-xs text-muted">
              Showing the latest of {uploads.length} uploads.
            </p>
          )}
        </Card>
      )}

      <Card className="mt-6">
        <CardHeader
          title="Scene catalogue"
          description="Which Sentinel scenes actually exist over this farm. A gap between usable passes longer than a dry-down is a blind spot."
        />
        <form className="grid gap-3 p-5 sm:grid-cols-4">
          <input type="hidden" name="scenes" value="1" />
          {q.season && <input type="hidden" name="season" value={q.season} />}
          <Field label="Sensor">
            <Select name="sensor" defaultValue={sensor}>
              <option value="s1">Sentinel-1 radar</option>
              <option value="s2">Sentinel-2 optical</option>
            </Select>
          </Field>
          <Field label="From">
            <Input type="date" name="from" defaultValue={from} />
          </Field>
          <Field label="To">
            <Input type="date" name="to" defaultValue={to} />
          </Field>
          <div className="flex items-end">
            <Button type="submit" variant="secondary" className="w-full">
              Search catalogue
            </Button>
          </div>
        </form>
        {sceneProblem && (
          <div className="px-5 pb-5">
            <Notice tone="accent">{sceneProblem}</Notice>
          </div>
        )}
        {coverage && (
          <div className="border-t border-border p-5">
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Scenes" value={coverage.scenes} hint={coverage.platforms.join(", ") || undefined} />
              <Stat label="Usable days" value={coverage.usable_days} />
              <Stat
                label="Median revisit"
                value={coverage.median_revisit_days == null ? "—" : `${coverage.median_revisit_days} d`}
              />
              <Stat
                label="Longest gap"
                value={`${coverage.max_gap_days} d`}
                tone={coverage.max_gap_days > 12 ? "accent" : "brand"}
                hint={coverage.max_gap_days > 12 ? "a dry-down could be missed" : "resolves a 2-week dry-down"}
              />
            </div>
            {coverage.scene_list.length ? (
              <SceneTimeline scenes={coverage.scene_list} />
            ) : (
              <EmptyState title="No scenes in that window" />
            )}
          </div>
        )}
      </Card>
    </>
  );
}

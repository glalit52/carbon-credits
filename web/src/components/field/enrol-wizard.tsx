"use client";

import { Camera, Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button, Card, cx, Field, Input, Notice, Select } from "@/components/ui";
import type { Language, Pathway, RiceEcosystem, Tenure, WaterControl } from "@/lib/database.types";
import { type FarmerChoice, type FieldDraft, queue } from "@/lib/field-queue";
import { validate } from "@/lib/geo";
import { LANGUAGES, translator } from "@/lib/i18n";

import { type Corner, GpsWalk, ringOf } from "./gps-walk";
import { sendQueued } from "./queue-list";
import { useOnline } from "./shell";

type FarmerOption = { id: string; name: string; village: string | null; external_ref: string | null };
type ProjectOption = { id: string; name: string; pathway: Pathway };

const TENURES: Tenure[] = ["owned_title", "registered_lease", "community_right", "grama_sabha_consent", "undocumented"];
const ECOSYSTEMS = ["irrigated_lowland", "rainfed", "upland", "deepwater"] as const satisfies readonly RiceEcosystem[];

/** Phone photos are large; a long edge of 1600 px keeps a form legible at a fifth of the size. */
async function shrink(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = new OffscreenCanvas(Math.round(bitmap.width * scale), Math.round(bitmap.height * scale));
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await canvas.convertToBlob({ type: "image/jpeg", quality: 0.8 });
  } catch {
    return file;
  }
}

function PhotoInput({ label, value, onChange }: { label: string; value: Blob | null; onChange: (b: Blob | null) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-3 text-sm">
      {value ? <Check className="h-5 w-5 text-brand" /> : <Camera className="h-5 w-5 text-muted" />}
      <span className="flex-1">{label}</span>
      {value && <span className="text-xs text-muted">{Math.round(value.size / 1024)} KB</span>}
      <input
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          onChange(f ? await shrink(f) : null);
        }}
      />
    </label>
  );
}

export function EnrolWizard({
  lang,
  farmers,
  projects,
}: {
  lang: Language;
  farmers: FarmerOption[];
  projects: ProjectOption[];
}) {
  const t = translator(lang);
  const router = useRouter();
  const online = useOnline();
  const [step, setStep] = useState(0);

  // Farmer
  const [mode, setMode] = useState<"existing" | "new">(farmers.length ? "existing" : "new");
  const [search, setSearch] = useState("");
  const [farmerId, setFarmerId] = useState<string | null>(null);
  const [nf, setNf] = useState({ name: "", phone: "", village: "", language: lang as Language, consent: false });
  const [consentPhoto, setConsentPhoto] = useState<Blob | null>(null);
  // Boundary
  const [corners, setCorners] = useState<Corner[]>([]);
  // Land
  const [projectId, setProjectId] = useState<string>(projects[0]?.id ?? "");
  const project = projects.find((p) => p.id === projectId);
  const rice = project?.pathway === "rice";
  const [farmName, setFarmName] = useState("");
  const [tenure, setTenure] = useState<Tenure>("owned_title");
  const [tenureRef, setTenureRef] = useState("");
  const [tenurePhoto, setTenurePhoto] = useState<Blob | null>(null);
  const [ecosystem, setEcosystem] = useState<RiceEcosystem>("irrigated_lowland");
  const [control, setControl] = useState<WaterControl>("full");
  const [saved, setSaved] = useState<"queued" | "sent" | null>(null);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    return farmers
      .filter((f) => !q || [f.name, f.village, f.external_ref].some((x) => x?.toLowerCase().includes(q)))
      .slice(0, 30);
  }, [farmers, search]);

  const geometry = ringOf(corners);
  const farmer: FarmerChoice | null =
    mode === "existing"
      ? farmerId
        ? { mode, id: farmerId, name: farmers.find((f) => f.id === farmerId)?.name ?? "" }
        : null
      : nf.name.trim()
        ? { mode, ...nf }
        : null;

  const problems = [
    !farmer && t("step.farmer"),
    mode === "new" && !nf.consent && t("farmer.consent"),
    (!geometry || validate(geometry).length > 0) && t("step.boundary"),
    !farmName.trim() && t("land.farm_name"),
  ].filter(Boolean) as string[];

  const steps = [t("step.farmer"), t("step.boundary"), t("step.land"), t("step.review")];

  async function save() {
    if (!farmer || !geometry || problems.length) return;
    const draft: FieldDraft = {
      id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      farmer,
      consent_photo: mode === "new" ? consentPhoto : null,
      boundary: geometry,
      corners,
      farm: {
        name: farmName.trim(),
        project_id: projectId || null,
        tenure,
        tenure_reference: tenureRef,
        rice_ecosystem: rice ? ecosystem : null,
        water_control: rice ? control : null,
        practice: rice ? "awd" : project?.pathway === "agroforestry" ? "shade_trees" : "",
      },
      tenure_photo: tenurePhoto,
      status: "queued",
    };
    await queue.put(draft);
    if (online) {
      await sendQueued();
      const after = (await queue.all()).find((d) => d.id === draft.id);
      setSaved(after?.status === "sent" ? "sent" : "queued");
    } else {
      setSaved("queued");
    }
  }

  if (saved) {
    return (
      <div className="flex flex-col gap-4">
        <Notice tone={saved === "sent" ? "brand" : "info"}>
          {saved === "sent" ? t("review.saved") : t("review.saved_offline")}
        </Notice>
        <Button type="button" onClick={() => router.push("/field")} className="py-4">
          {t("common.next")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <ol className="grid grid-cols-4 gap-1 text-center text-[11px]">
        {steps.map((s, i) => (
          <li key={s}>
            <button
              type="button"
              onClick={() => setStep(i)}
              className={cx(
                "w-full border-b-2 pb-1",
                i === step ? "border-brand font-semibold text-brand" : i < step ? "border-brand/40 text-text" : "border-border text-muted",
              )}
            >
              {i + 1}. {s}
            </button>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-2">
            {(["existing", "new"] as const).map((m) => (
              <Button key={m} type="button" variant={mode === m ? "primary" : "secondary"} onClick={() => setMode(m)}>
                {m === "existing" ? t("farmer.existing") : t("farmer.new")}
              </Button>
            ))}
          </div>
          {mode === "existing" ? (
            <>
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("farmer.search")} />
              <Card>
                <ul className="max-h-80 divide-y divide-border overflow-y-auto">
                  {matches.map((f) => (
                    <li key={f.id}>
                      <button
                        type="button"
                        onClick={() => setFarmerId(f.id)}
                        className={cx("flex w-full items-center justify-between px-4 py-3 text-left text-sm", farmerId === f.id && "bg-brand-soft")}
                      >
                        <span>
                          <span className="font-medium">{f.name}</span>
                          <span className="block text-xs text-muted">
                            {[f.village, f.external_ref].filter(Boolean).join(" · ")}
                          </span>
                        </span>
                        {farmerId === f.id && <Check className="h-4 w-4 text-brand" />}
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            </>
          ) : (
            <>
              <Field label={t("farmer.name")}>
                <Input value={nf.name} onChange={(e) => setNf({ ...nf, name: e.target.value })} autoComplete="off" />
              </Field>
              <Field label={t("farmer.phone")}>
                <Input type="tel" value={nf.phone} onChange={(e) => setNf({ ...nf, phone: e.target.value })} />
              </Field>
              <Field label={t("farmer.village")}>
                <Input value={nf.village} onChange={(e) => setNf({ ...nf, village: e.target.value })} />
              </Field>
              <Field label={t("farmer.language")}>
                <Select value={nf.language} onChange={(e) => setNf({ ...nf, language: e.target.value as Language })}>
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.native}
                    </option>
                  ))}
                </Select>
              </Field>
              <label className="flex items-start gap-3 rounded-lg border border-border bg-surface p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-5 w-5"
                  checked={nf.consent}
                  onChange={(e) => setNf({ ...nf, consent: e.target.checked })}
                />
                {t("farmer.consent")}
              </label>
              <PhotoInput label={t("farmer.consent_photo")} value={consentPhoto} onChange={setConsentPhoto} />
            </>
          )}
        </div>
      )}

      {step === 1 && <GpsWalk corners={corners} onChange={setCorners} t={t} />}

      {step === 2 && (
        <div className="flex flex-col gap-4">
          <Field label={t("land.farm_name")}>
            <Input value={farmName} onChange={(e) => setFarmName(e.target.value)} />
          </Field>
          {projects.length > 0 && (
            <Field label={t("land.project")}>
              <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label={t("land.tenure")}>
            <Select value={tenure} onChange={(e) => setTenure(e.target.value as Tenure)}>
              {TENURES.map((x) => (
                <option key={x} value={x}>
                  {t(`tenure.${x}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("land.tenure_ref")}>
            <Input value={tenureRef} onChange={(e) => setTenureRef(e.target.value)} />
          </Field>
          <PhotoInput label={t("land.tenure_photo")} value={tenurePhoto} onChange={setTenurePhoto} />
          {rice && (
            <>
              <Field label={t("land.ecosystem")}>
                <Select value={ecosystem} onChange={(e) => setEcosystem(e.target.value as RiceEcosystem)}>
                  {ECOSYSTEMS.map((x) => (
                    <option key={x} value={x}>
                      {t(`eco.${x}`)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={t("land.water_control")}>
                <Select value={control} onChange={(e) => setControl(e.target.value as WaterControl)}>
                  <option value="full">{t("common.yes")}</option>
                  <option value="none">{t("common.no")}</option>
                  <option value="unknown">{t("common.unknown")}</option>
                </Select>
              </Field>
            </>
          )}
        </div>
      )}

      {step === 3 && (
        <div className="flex flex-col gap-4">
          {problems.length ? (
            <Notice tone="accent" title={t("review.problems")}>
              <ul className="list-disc pl-4">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </Notice>
          ) : (
            <Notice tone="brand">{t("review.ready")}</Notice>
          )}
          <Card className="divide-y divide-border text-sm">
            <Row k={t("step.farmer")} v={farmer?.name ?? "—"} />
            <Row k={t("land.farm_name")} v={farmName || "—"} />
            <Row k={t("boundary.corners")} v={String(corners.length)} />
            <Row k={t("land.tenure")} v={`${t(`tenure.${tenure}`)}${tenureRef ? ` · ${tenureRef}` : ""}`} />
          </Card>
          <Button type="button" className="py-4 text-base" disabled={problems.length > 0} onClick={() => void save()}>
            {t("review.save")}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Button type="button" variant="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>
          {t("common.back")}
        </Button>
        {step < 3 && (
          <Button type="button" onClick={() => setStep(step + 1)}>
            {t("common.next")}
          </Button>
        )}
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 px-4 py-2">
      <span className="text-muted">{k}</span>
      <span className="text-right font-medium">{v}</span>
    </div>
  );
}

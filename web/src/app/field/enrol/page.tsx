import { EnrolWizard } from "@/components/field/enrol-wizard";
import { getOrgContext, listFarmers, listProjects } from "@/lib/data";
import { fieldLanguage } from "@/lib/field-lang";
import { translator } from "@/lib/i18n";

export default async function FieldEnrol() {
  const ctx = await getOrgContext();
  const [lang, farmers, projects] = await Promise.all([fieldLanguage(), listFarmers(ctx.org.id), listProjects(ctx.org.id)]);
  const t = translator(lang);
  return (
    <>
      <h1 className="mb-4 text-xl font-semibold">{t("field.enrol")}</h1>
      <EnrolWizard
        lang={lang}
        farmers={farmers.map((f) => ({ id: f.id, name: f.name, village: f.village, external_ref: f.external_ref }))}
        projects={projects.filter((p) => p.status !== "closed").map((p) => ({ id: p.id, name: p.name, pathway: p.pathway }))}
      />
    </>
  );
}

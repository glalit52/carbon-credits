import "server-only";

import { cookies } from "next/headers";

import type { Language } from "@/lib/database.types";
import { FIELD_LANG_COOKIE, isLanguage } from "@/lib/i18n";

/** The field app's language: the agent's own choice, kept in a cookie. */
export async function fieldLanguage(): Promise<Language> {
  const v = (await cookies()).get(FIELD_LANG_COOKIE)?.value;
  return isLanguage(v) ? v : "en";
}

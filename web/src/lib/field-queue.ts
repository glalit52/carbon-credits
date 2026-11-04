// Enrolments made in the field wait here, on the phone, until they are sent.
// IndexedDB rather than localStorage because photos are Blobs and a day's
// enrolments can run to tens of megabytes.

import type { Language, PolygonGeometry, RiceEcosystem, Tenure, WaterControl } from "@/lib/database.types";

export type FarmerChoice =
  | { mode: "existing"; id: string; name: string }
  | { mode: "new"; name: string; phone: string; village: string; language: Language; consent: boolean };

export type FieldDraft = {
  /** Generated on the phone; the server uses it so a resend cannot enrol a farm twice. */
  id: string;
  created_at: string;
  farmer: FarmerChoice;
  consent_photo: Blob | null;
  boundary: PolygonGeometry;
  corners: { lon: number; lat: number; accuracy_m: number; at: string }[];
  farm: {
    name: string;
    project_id: string | null;
    tenure: Tenure;
    tenure_reference: string;
    rice_ecosystem: RiceEcosystem | null;
    water_control: WaterControl | null;
    practice: string;
  };
  tenure_photo: Blob | null;
  status: "queued" | "sending" | "failed" | "sent";
  error?: string;
  farm_id?: string;
};

const DB = "carbonstack-field";
const STORE = "drafts";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export const queue = {
  all: () => tx<FieldDraft[]>("readonly", (s) => s.getAll() as IDBRequest<FieldDraft[]>),
  put: (d: FieldDraft) => tx("readwrite", (s) => s.put(d)),
  remove: (id: string) => tx("readwrite", (s) => s.delete(id)),
};

/** Turn a draft into the form the server action reads. */
export function toFormData(d: FieldDraft): FormData {
  const form = new FormData();
  const { consent_photo, tenure_photo, ...rest } = d;
  form.set("draft", JSON.stringify({ ...rest, status: undefined, error: undefined }));
  if (consent_photo) form.set("consent_photo", consent_photo, "consent.jpg");
  if (tenure_photo) form.set("tenure_photo", tenure_photo, "land-record.jpg");
  return form;
}

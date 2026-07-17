// Pure logic for the Drug Interaction Studio: searching the library, building a drug
// regimen (add / remove / dose), and exporting it. No React, no Three — unit-testable.

import type { Drug, DrugDose } from "../../api/types";

/** Case-insensitive search across name, description, mechanism and targets. */
export function filterDrugs(drugs: Drug[], query: string): Drug[] {
  const q = query.trim().toLowerCase();
  if (!q) return drugs;
  return drugs.filter((d) =>
    [d.name, d.description, d.mechanism, ...d.targets].join(" ").toLowerCase().includes(q),
  );
}

/** Add a drug to the regimen at its default dose (no duplicates — same drug once). */
export function addDrug(regimen: DrugDose[], drug: Drug): DrugDose[] {
  if (regimen.some((r) => r.drug_id === drug.id)) return regimen;
  return [...regimen, { drug_id: drug.id, dose: drug.default_dose, start_time: 0 }];
}

export function removeDrug(regimen: DrugDose[], drugId: string): DrugDose[] {
  return regimen.filter((r) => r.drug_id !== drugId);
}

/** Set the dose for one drug (clamped to the studio's 0–2× range). */
export function setDose(regimen: DrugDose[], drugId: string, dose: number): DrugDose[] {
  const d = Math.max(0, Math.min(2, dose));
  return regimen.map((r) => (r.drug_id === drugId ? { ...r, dose: d } : r));
}

export function isActive(regimen: DrugDose[], drugId: string): boolean {
  return regimen.some((r) => r.drug_id === drugId);
}

/** A short human summary of the regimen (for markers / history). */
export function summarizeRegimen(regimen: DrugDose[], drugs: Drug[]): string {
  if (!regimen.length) return "Untreated";
  const byId = new Map(drugs.map((d) => [d.id, d]));
  return regimen
    .map((r) => `${byId.get(r.drug_id)?.name ?? r.drug_id} ${r.dose.toFixed(1)}×`)
    .join(" + ");
}

/** Export the regimen (with resolved names/mechanisms) as a JSON experiment record. */
export function exportRegimen(regimen: DrugDose[], drugs: Drug[]): string {
  const byId = new Map(drugs.map((d) => [d.id, d]));
  const record = {
    kind: "drug-interaction-experiment",
    drugs: regimen.map((r) => ({
      ...r,
      name: byId.get(r.drug_id)?.name,
      mechanism: byId.get(r.drug_id)?.mechanism,
    })),
  };
  return JSON.stringify(record, null, 2);
}

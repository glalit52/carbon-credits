"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { FieldCheckView } from "@/components/checker/field-check-view";
import { FieldComparator } from "@/components/checker/field-comparator";
import { LocationPicker } from "@/components/checker/location-picker";
import { PrintableReport } from "@/components/checker/printable-report";
import { SavedFieldsDrawer } from "@/components/checker/saved-fields-drawer";
import { Button, PageHeader } from "@/components/ui";

import {
  type CheckInput,
  type CheckResult,
  evaluateField,
  POPULAR_PRESETS,
  synthesizeBoundary,
} from "@/lib/checker-engine";
import {
  getSavedFields,
  type SavedFieldRecord,
  saveField,
  updateField,
} from "@/lib/saved-locations-store";

export default function FieldCheckerPage() {
  const [savedFields, setSavedFields] = useState<SavedFieldRecord[]>(() => getSavedFields());

  const defaultPreset = POPULAR_PRESETS[0];
  const initialBoundary = synthesizeBoundary(defaultPreset.lat, defaultPreset.lon, defaultPreset.area_ha);

  const [activeFieldId, setActiveFieldId] = useState<string | undefined>(() => savedFields[0]?.id);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [showPrintModal, setShowPrintModal] = useState(false);

  const [currentInput, setCurrentInput] = useState<CheckInput>(() => {
    return savedFields[0]?.input ?? {
      name: "Kaveri Delta Paddy Plot",
      lat: defaultPreset.lat,
      lon: defaultPreset.lon,
      area_ha: defaultPreset.area_ha,
      boundary: initialBoundary,
      pathway: defaultPreset.pathway,
      crop: defaultPreset.crop,
      practice: defaultPreset.practice,
      tenure: "owned_title",
      tenure_reference: "PATTA-TNJ-2024-0042",
      farmer_name: "Murugan Swaminathan",
      rice_ecosystem: defaultPreset.rice_ecosystem,
      water_control: defaultPreset.water_control,
      seasons_per_year: defaultPreset.seasons_per_year,
      season_days: defaultPreset.season_days,
      measurement_tier: 2,
      carbon_price_usd: 15.0,
      farmer_share_pct: 60.0,
      monitoring_cost_per_ha: 6.2,
    };
  });

  const [currentResult, setCurrentResult] = useState<CheckResult>(() => {
    return savedFields[0]?.result ?? evaluateField(currentInput);
  });

  const refreshSavedFields = () => {
    setSavedFields(getSavedFields());
  };

  const handleRunCheck = () => {
    const res = evaluateField(currentInput);
    setCurrentResult(res);
  };

  const handleSaveOrUpdate = () => {
    if (activeFieldId) {
      updateField(activeFieldId, currentInput);
      refreshSavedFields();
    } else {
      const saved = saveField(currentInput, ["Manual Check"]);
      setActiveFieldId(saved.id);
      refreshSavedFields();
    }
  };

  const handleSelectField = (record: SavedFieldRecord) => {
    setActiveFieldId(record.id);
    setCurrentInput(record.input);
    setCurrentResult(record.result);
  };

  const handleNewCheck = () => {
    const preset = POPULAR_PRESETS[Math.floor(Math.random() * POPULAR_PRESETS.length)];
    const boundary = synthesizeBoundary(preset.lat, preset.lon, preset.area_ha);
    const newInput: CheckInput = {
      name: `New ${preset.title} Plot`,
      lat: preset.lat,
      lon: preset.lon,
      area_ha: preset.area_ha,
      boundary,
      pathway: preset.pathway,
      crop: preset.crop,
      practice: preset.practice,
      tenure: "owned_title",
      tenure_reference: "",
      rice_ecosystem: preset.rice_ecosystem,
      water_control: preset.water_control,
      seasons_per_year: preset.seasons_per_year,
      season_days: preset.season_days,
      stems_planted_per_ha: preset.stems_planted_per_ha ?? 120,
      tree_species: preset.tree_species,
      measurement_tier: 2,
      carbon_price_usd: 15.0,
      farmer_share_pct: 60.0,
      monitoring_cost_per_ha: 6.2,
    };
    setActiveFieldId(undefined);
    setCurrentInput(newInput);
    setCurrentResult(evaluateField(newInput));
  };

  const fieldsToCompare = savedFields.filter((f) => compareIds.includes(f.id));

  return (
    <>
      <PageHeader
        title="Field & Location Checker"
        crumbs={[{ href: "/app", label: "App" }, { href: "/app/checker", label: "Checker" }]}
        description="Add manual fields, test coordinates anywhere on earth, run carbon credit & dMRV feasibility assessments, and save them for reuse."
        actions={
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" onClick={handleNewCheck} className="text-xs">
              <Plus className="h-3.5 w-3.5" /> New Assessment
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-12 items-start">
        {/* Left Column: Form & Map Picker (7 cols on lg) */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <LocationPicker
            value={currentInput}
            onChange={(val) => {
              setCurrentInput(val);
              // auto-evaluate on input change so feedback is instantaneous
              setCurrentResult(evaluateField(val));
            }}
            onRunCheck={handleRunCheck}
            onSave={handleSaveOrUpdate}
            isSaved={Boolean(activeFieldId)}
          />

          <FieldCheckView
            input={currentInput}
            result={currentResult}
            onSave={handleSaveOrUpdate}
            isSaved={Boolean(activeFieldId)}
            onPrint={() => setShowPrintModal(true)}
          />
        </div>

        {/* Right Column: Saved Locations Drawer (5 cols on lg) */}
        <div className="lg:col-span-5 sticky top-4">
          <SavedFieldsDrawer
            fields={savedFields}
            activeFieldId={activeFieldId}
            onSelect={handleSelectField}
            onRefresh={refreshSavedFields}
            onCompare={(ids) => setCompareIds(ids)}
          />
        </div>
      </div>

      {/* Comparison Modal */}
      {fieldsToCompare.length > 0 && (
        <FieldComparator
          fields={fieldsToCompare}
          onClose={() => setCompareIds([])}
          onSelectField={(f) => {
            handleSelectField(f);
            setCompareIds([]);
          }}
        />
      )}

      {/* Printable Report Modal */}
      {showPrintModal && (
        <PrintableReport
          input={currentInput}
          result={currentResult}
          onClose={() => setShowPrintModal(false)}
        />
      )}
    </>
  );
}

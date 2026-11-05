"use client";

import {
  CheckSquare,
  Download,
  FileSpreadsheet,
  RefreshCw,
  Search,
  Square,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button, Card, CardHeader, Input } from "@/components/ui";

import {
  deleteField,
  exportFieldsCSV,
  exportFieldsGeoJSON,
  getDefaultSeedFields,
  type SavedFieldRecord,
  toggleStarField,
} from "@/lib/saved-locations-store";

interface SavedFieldsDrawerProps {
  fields: SavedFieldRecord[];
  activeFieldId?: string;
  onSelect: (record: SavedFieldRecord) => void;
  onRefresh: () => void;
  onCompare: (selectedIds: string[]) => void;
}

export function SavedFieldsDrawer({
  fields,
  activeFieldId,
  onSelect,
  onRefresh,
  onCompare,
}: SavedFieldsDrawerProps) {
  const [search, setSearch] = useState("");
  const [pathwayFilter, setPathwayFilter] = useState<string>("all");
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);

  const filtered = useMemo(() => {
    return fields.filter((f) => {
      const matchSearch =
        search === "" ||
        f.name.toLowerCase().includes(search.toLowerCase()) ||
        f.input.farmer_name?.toLowerCase().includes(search.toLowerCase()) ||
        f.tags?.some((t) => t.toLowerCase().includes(search.toLowerCase()));

      const matchPathway = pathwayFilter === "all" || f.input.pathway === pathwayFilter;

      return matchSearch && matchPathway;
    });
  }, [fields, search, pathwayFilter]);

  const handleToggleStar = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    toggleStarField(id);
    onRefresh();
  };

  const handleDelete = (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm(`Delete saved field "${name}"?`)) {
      deleteField(id);
      setSelectedForCompare((prev) => prev.filter((x) => x !== id));
      onRefresh();
    }
  };

  const toggleCompare = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedForCompare((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) {
        alert("You can compare up to 3 fields side-by-side.");
        return prev;
      }
      return [...prev, id];
    });
  };

  const handleExportGeoJSON = () => {
    const raw = exportFieldsGeoJSON();
    const blob = new Blob([raw], { type: "application/geo+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `carbonstack-saved-fields-${new Date().toISOString().slice(0, 10)}.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportCSV = () => {
    const raw = exportFieldsCSV();
    const blob = new Blob([raw], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `carbonstack-saved-fields-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleResetPresets = () => {
    if (confirm("Reset saved fields back to the standard sample presets?")) {
      localStorage.setItem("carbonstack_saved_fields_v1", JSON.stringify(getDefaultSeedFields()));
      onRefresh();
    }
  };

  return (
    <Card className="flex flex-col h-full">
      <CardHeader
        title={
          <div className="flex items-center gap-2">
            <span>Saved Fields & Locations</span>
            <span className="rounded-full bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand-strong">
              {fields.length}
            </span>
          </div>
        }
        description="Locations stored locally in your browser session for testing and MRV checks."
        action={
          <div className="flex items-center gap-1.5">
            <Button
              type="button"
              variant="secondary"
              className="text-xs py-1 px-2.5"
              onClick={handleExportGeoJSON}
              title="Export all saved fields as GeoJSON"
            >
              <Download className="h-3 w-3" /> GeoJSON
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="text-xs py-1 px-2.5"
              onClick={handleExportCSV}
              title="Export table as CSV"
            >
              <FileSpreadsheet className="h-3 w-3" /> CSV
            </Button>
          </div>
        }
      />

      <div className="p-3 border-b border-border flex flex-col gap-2 bg-surface-2/30">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input
            placeholder="Search saved fields by name or farmer..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 text-xs py-1.5"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-2.5 top-2.5 text-muted hover:text-text"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-1.5 text-xs">
          <div className="flex gap-1">
            {["all", "rice", "agroforestry", "soil"].map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPathwayFilter(p)}
                className={`rounded-md px-2 py-0.5 capitalize transition ${
                  pathwayFilter === p
                    ? "bg-brand text-white font-medium"
                    : "text-muted hover:bg-surface-2 hover:text-text"
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          {selectedForCompare.length > 0 && (
            <Button
              type="button"
              variant="primary"
              className="text-xs py-0.5 px-2"
              onClick={() => onCompare(selectedForCompare)}
            >
              Compare ({selectedForCompare.length})
            </Button>
          )}
        </div>
      </div>

      {/* Field Cards List */}
      <div className="flex-1 overflow-y-auto divide-y divide-border p-2 space-y-2 max-h-[620px]">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted">
            No saved fields match your query. Add a new manual location or reset to presets.
            <div className="mt-3">
              <Button type="button" variant="secondary" onClick={handleResetPresets} className="text-xs">
                <RefreshCw className="h-3 w-3" /> Reset to presets
              </Button>
            </div>
          </div>
        ) : (
          filtered.map((record) => {
            const isSelected = record.id === activeFieldId;
            const isChecked = selectedForCompare.includes(record.id);

            return (
              <div
                key={record.id}
                onClick={() => onSelect(record)}
                className={`group relative flex flex-col gap-2 rounded-xl border p-3 cursor-pointer transition ${
                  isSelected
                    ? "border-brand bg-brand-soft/30 shadow-xs"
                    : "border-border bg-surface hover:border-brand/40 hover:bg-surface-2/40"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <button
                      type="button"
                      onClick={(e) => toggleCompare(record.id, e)}
                      className="mt-0.5 text-muted hover:text-brand"
                      title="Select to compare side-by-side"
                    >
                      {isChecked ? (
                        <CheckSquare className="h-4 w-4 text-brand" />
                      ) : (
                        <Square className="h-4 w-4" />
                      )}
                    </button>
                    <div>
                      <h4 className="font-semibold text-xs sm:text-sm text-text leading-tight group-hover:text-brand transition">
                        {record.name}
                      </h4>
                      <p className="text-[11px] text-muted mt-0.5">
                        {record.input.farmer_name ? `${record.input.farmer_name} · ` : ""}
                        {record.input.area_ha.toFixed(2)} ha ({(record.input.area_ha * 2.471).toFixed(2)} ac) ·{" "}
                        <span className="capitalize">{record.input.pathway}</span>
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(e) => handleToggleStar(record.id, e)}
                      className={`p-1 transition ${record.starred ? "text-amber-500" : "text-muted hover:text-amber-500"}`}
                      title={record.starred ? "Starred" : "Star field"}
                    >
                      <Star className="h-3.5 w-3.5 fill-current" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => handleDelete(record.id, record.name, e)}
                      className="p-1 text-muted hover:text-danger opacity-0 group-hover:opacity-100 transition"
                      title="Delete saved field"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-1 rounded-lg bg-surface-2/60 p-1.5 text-center text-[10px]">
                  <div>
                    <span className="text-muted block">Net Credits</span>
                    <strong className="text-brand tabular">{record.result.netCreditsTonnesYear} t</strong>
                  </div>
                  <div>
                    <span className="text-muted block">Farmer Payout</span>
                    <strong className="text-brand-strong tabular">
                      ${record.result.annualFarmerPayoutUSD.toLocaleString()}
                    </strong>
                  </div>
                  <div>
                    <span className="text-muted block">Status</span>
                    <strong
                      className={`capitalize ${
                        record.result.eligibility === "PASS"
                          ? "text-brand"
                          : record.result.eligibility === "CONDITIONAL"
                          ? "text-accent"
                          : "text-danger"
                      }`}
                    >
                      {record.result.eligibility}
                    </strong>
                  </div>
                </div>

                {record.tags && record.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {record.tags.map((t, idx) => (
                      <span
                        key={idx}
                        className="rounded-full bg-surface-2 px-1.5 py-0.2 text-[9px] font-medium text-muted"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="p-3 border-t border-border flex items-center justify-between text-xs text-muted bg-surface-2/20">
        <span>Click any field to load analysis.</span>
        <button
          type="button"
          onClick={handleResetPresets}
          className="text-brand hover:underline font-medium text-[11px]"
        >
          Reset Presets
        </button>
      </div>
    </Card>
  );
}

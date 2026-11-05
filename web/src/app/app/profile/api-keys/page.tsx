"use client";

import { Check, Copy, KeyRound, Plus, Terminal } from "lucide-react";
import { useState } from "react";

import { ProfileNav } from "@/components/profile/profile-nav";
import { Button, Card, CardHeader, Field, Input, Notice, PageHeader, Table, Td, Th } from "@/components/ui";

interface ApiKeyItem {
  id: string;
  name: string;
  keyPrefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  scopes: string[];
}

const INITIAL_KEYS: ApiKeyItem[] = [
  {
    id: "key-1",
    name: "CLI Development Token (Macbook Pro)",
    keyPrefix: "cstk_live_9a7b...4e1d",
    createdAt: "2026-10-10",
    lastUsedAt: "Today, 11:42 AM",
    scopes: ["read:estimates", "write:farms", "run:forecast"],
  },
  {
    id: "key-2",
    name: "Automated Satellite Ingestion Pipeline",
    keyPrefix: "cstk_live_41c0...92b7",
    createdAt: "2026-09-18",
    lastUsedAt: "Yesterday, 04:15 PM",
    scopes: ["read:telemetry", "write:sensors", "read:scenes"],
  },
];

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyItem[]>(INITIAL_KEYS);
  const [newKeyName, setNewKeyName] = useState("");
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;

    const rawToken = `cstk_live_${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
    const newItem: ApiKeyItem = {
      id: `key-${Date.now()}`,
      name: newKeyName.trim(),
      keyPrefix: `${rawToken.slice(0, 14)}...${rawToken.slice(-4)}`,
      createdAt: new Date().toISOString().slice(0, 10),
      lastUsedAt: "Just now",
      scopes: ["read:estimates", "write:farms", "audit:vintages"],
    };

    setKeys([newItem, ...keys]);
    setGeneratedKey(rawToken);
    setNewKeyName("");
  };

  const handleRevoke = (id: string, name: string) => {
    if (confirm(`Revoke API key "${name}"? Any automated script using it will stop working.`)) {
      setKeys(keys.filter((k) => k.id !== id));
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <>
      <PageHeader
        title="Developer & API Tokens"
        crumbs={[{ href: "/app/profile", label: "Profile" }, { href: "/app/profile/api-keys", label: "API Keys" }]}
        description="Manage personal access tokens and engine authentication for the CLI and external integrations."
      />
      <ProfileNav />

      {generatedKey && (
        <div className="mb-6">
          <Notice tone="brand" title="Your New API Token Generated">
            <p className="text-xs mb-2">
              Make sure to copy your API key now as you won&apos;t be able to see it again!
            </p>
            <div className="flex items-center gap-2 font-mono text-xs bg-surface p-2.5 rounded-lg border border-border">
              <span className="flex-1 truncate select-all">{generatedKey}</span>
              <Button
                type="button"
                variant="secondary"
                className="text-xs py-1 px-2.5"
                onClick={() => copyToClipboard(generatedKey)}
              >
                {copied ? <Check className="h-3.5 w-3.5 text-brand" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </Notice>
        </div>
      )}

      <div className="flex flex-col gap-6">
        {/* Generate New Key Card */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-brand" />
                <span>Create New Personal Access Token</span>
              </div>
            }
            description="Allows authenticated API calls to POST /api/estimate, forecast, and CLI synchronization."
          />
          <form onSubmit={handleCreate} className="p-5 flex flex-col sm:flex-row items-end gap-3">
            <Field label="Key Name / Description" className="flex-1">
              <Input
                placeholder="e.g. Field Data Collector or QGIS Script"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                required
              />
            </Field>
            <Button type="submit" className="py-2.5">
              <Plus className="h-4 w-4" /> Generate Token
            </Button>
          </form>
        </Card>

        {/* Existing Keys Table */}
        <Card>
          <CardHeader
            title="Active API Keys"
            description={`${keys.length} active developer keys in your account.`}
          />
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Token Identifier</Th>
                <Th>Created</Th>
                <Th>Last Used</Th>
                <Th>Scopes</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <Td className="font-semibold text-xs sm:text-sm">{k.name}</Td>
                  <Td className="font-mono text-xs text-muted">{k.keyPrefix}</Td>
                  <Td className="text-xs tabular">{k.createdAt}</Td>
                  <Td className="text-xs tabular text-muted">{k.lastUsedAt ?? "Never"}</Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {k.scopes.map((s) => (
                        <span key={s} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-mono text-muted">
                          {s}
                        </span>
                      ))}
                    </div>
                  </Td>
                  <Td>
                    <button
                      type="button"
                      onClick={() => handleRevoke(k.id, k.name)}
                      className="text-xs text-danger hover:underline font-medium"
                    >
                      Revoke
                    </button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        {/* CLI & Integration Quick Start */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-brand" />
                <span>CLI & Python SDK Authentication</span>
              </div>
            }
            description="Use your token in the terminal or Python scripts."
          />
          <div className="p-5 flex flex-col gap-4 text-xs font-mono">
            <div className="rounded-lg bg-surface-2 p-3 text-text leading-relaxed">
              <span className="text-muted block font-sans text-[11px] mb-1 font-semibold">Terminal / Bash:</span>
              export CARBONSTACK_ENGINE_TOKEN=&quot;cstk_live_...&quot;
              <br />
              python3 -m carbonstack quantify project.json --year 2026 --methodology VM0051
            </div>

            <div className="rounded-lg bg-surface-2 p-3 text-text leading-relaxed">
              <span className="text-muted block font-sans text-[11px] mb-1 font-semibold">REST API Header:</span>
              Authorization: Bearer cstk_live_...
              <br />
              Content-Type: application/json
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}

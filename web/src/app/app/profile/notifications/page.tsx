"use client";

import { Mail, MessageSquare, Webhook } from "lucide-react";
import { useState } from "react";

import { ProfileNav } from "@/components/profile/profile-nav";
import { Button, Card, CardHeader, Notice, PageHeader } from "@/components/ui";

interface NotificationConfig {
  emailAnomaly: boolean;
  emailVintageReview: boolean;
  emailIssuance: boolean;
  emailPayouts: boolean;
  smsUrgentAlerts: boolean;
  webhookEndpoint: string;
}

const DEFAULT_NOTIFS: NotificationConfig = {
  emailAnomaly: true,
  emailVintageReview: true,
  emailIssuance: true,
  emailPayouts: true,
  smsUrgentAlerts: false,
  webhookEndpoint: "https://api.yourdomain.com/webhooks/carbonstack",
};

export default function NotificationsPage() {
  const [config, setConfig] = useState<NotificationConfig>(DEFAULT_NOTIFS);
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <>
      <PageHeader
        title="Notification Preferences"
        crumbs={[{ href: "/app/profile", label: "Profile" }, { href: "/app/profile/notifications", label: "Notifications" }]}
        description="Choose when and how you receive alerts regarding telemetry anomalies, vintage reviews, and farmer payments."
      />
      <ProfileNav />

      {saved && (
        <div className="mb-6">
          <Notice tone="brand">✓ Notification settings updated successfully.</Notice>
        </div>
      )}

      <form onSubmit={handleSave} className="flex flex-col gap-6">
        {/* Email Notifications */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-brand" />
                <span>Email Notifications</span>
              </div>
            }
            description="Sent to your verified account email address."
          />
          <div className="divide-y divide-border">
            <label className="flex items-start justify-between p-4 cursor-pointer hover:bg-surface-2/30 transition">
              <div className="pr-4">
                <strong className="text-sm text-text block">Satellite MRV & Telemetry Anomalies</strong>
                <span className="text-xs text-muted">
                  Alerts when Sentinel-1 passes reveal an ambiguous water layer during required AWD dry spells or a sensor flatline.
                </span>
              </div>
              <input
                type="checkbox"
                checked={config.emailAnomaly}
                onChange={(e) => setConfig({ ...config, emailAnomaly: e.target.checked })}
                className="h-4 w-4 rounded accent-brand mt-1"
              />
            </label>

            <label className="flex items-start justify-between p-4 cursor-pointer hover:bg-surface-2/30 transition">
              <div className="pr-4">
                <strong className="text-sm text-text block">Four-Eyes Vintage Review Requests</strong>
                <span className="text-xs text-muted">
                  Notification when an analyst submits a vintage ready for second-reviewer examination and approval.
                </span>
              </div>
              <input
                type="checkbox"
                checked={config.emailVintageReview}
                onChange={(e) => setConfig({ ...config, emailVintageReview: e.target.checked })}
                className="h-4 w-4 rounded accent-brand mt-1"
              />
            </label>

            <label className="flex items-start justify-between p-4 cursor-pointer hover:bg-surface-2/30 transition">
              <div className="pr-4">
                <strong className="text-sm text-text block">Credit Issuance Confirmation</strong>
                <span className="text-xs text-muted">
                  Notifies when serials are minted and the immutable SHA-256 evidence pack is locked.
                </span>
              </div>
              <input
                type="checkbox"
                checked={config.emailIssuance}
                onChange={(e) => setConfig({ ...config, emailIssuance: e.target.checked })}
                className="h-4 w-4 rounded accent-brand mt-1"
              />
            </label>

            <label className="flex items-start justify-between p-4 cursor-pointer hover:bg-surface-2/30 transition">
              <div className="pr-4">
                <strong className="text-sm text-text block">Farmer Payouts & Batch Settlements</strong>
                <span className="text-xs text-muted">
                  Disbursement summaries and confirmation of recorded bank/mobile-money transaction references.
                </span>
              </div>
              <input
                type="checkbox"
                checked={config.emailPayouts}
                onChange={(e) => setConfig({ ...config, emailPayouts: e.target.checked })}
                className="h-4 w-4 rounded accent-brand mt-1"
              />
            </label>
          </div>
        </Card>

        {/* SMS Urgent Alerts */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-brand" />
                <span>SMS Field Alerts</span>
              </div>
            }
            description="Direct text alerts to verified mobile phones for field agents."
          />
          <div className="p-4">
            <label className="flex items-start justify-between cursor-pointer">
              <div className="pr-4">
                <strong className="text-sm text-text block">Critical Weather & Radar Revisit Warnings</strong>
                <span className="text-xs text-muted">
                  Sends SMS when a field parcel enters a multi-week cloud/rain blind gap requiring manual field verification.
                </span>
              </div>
              <input
                type="checkbox"
                checked={config.smsUrgentAlerts}
                onChange={(e) => setConfig({ ...config, smsUrgentAlerts: e.target.checked })}
                className="h-4 w-4 rounded accent-brand mt-1"
              />
            </label>
          </div>
        </Card>

        {/* Webhooks Integration */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Webhook className="h-4 w-4 text-brand" />
                <span>Automated Webhook Dispatch</span>
              </div>
            }
            description="Real-time HTTP POST JSON events for enterprise ERP or registry syncing."
          />
          <div className="p-5 flex flex-col gap-3">
            <label className="flex flex-col gap-1.5 text-xs">
              <span className="font-semibold text-text">Webhook Target URL</span>
              <input
                type="url"
                value={config.webhookEndpoint}
                onChange={(e) => setConfig({ ...config, webhookEndpoint: e.target.value })}
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-xs font-mono"
                placeholder="https://yourserver.com/api/carbonstack-events"
              />
              <span className="text-muted">Payloads signed via HMAC SHA-256 using your account API secret.</span>
            </label>
          </div>
        </Card>

        <div className="flex justify-end">
          <Button type="submit" className="py-2.5 px-6">
            Save Notification Settings
          </Button>
        </div>
      </form>
    </>
  );
}

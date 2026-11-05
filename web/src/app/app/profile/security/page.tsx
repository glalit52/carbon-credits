"use client";

import { CheckCircle2, Lock, MonitorSmartphone, QrCode, Shield, Smartphone } from "lucide-react";
import { useState } from "react";

import { ProfileNav } from "@/components/profile/profile-nav";
import { Badge, Button, Card, CardHeader, Field, Input, Notice, PageHeader, Table, Td, Th } from "@/components/ui";

const SESSIONS = [
  {
    id: "sess-1",
    device: "MacBook Pro (Chrome 130, macOS Sequoia)",
    location: "Chennai, India",
    ip: "157.48.21.90",
    current: true,
    lastActive: "Active now",
  },
  {
    id: "sess-2",
    device: "iPhone 15 Pro (Safari Mobile, iOS 18)",
    location: "Thanjavur, India",
    ip: "106.195.42.12",
    current: false,
    lastActive: "Yesterday at 05:22 PM",
  },
  {
    id: "sess-3",
    device: "Dell Precision (Firefox, Ubuntu Linux)",
    location: "Nairobi, Kenya",
    ip: "197.232.88.14",
    current: false,
    lastActive: "3 days ago",
  },
];

export default function SecurityPage() {
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
  const [showQRModal, setShowQRModal] = useState(false);
  const [sessions, setSessions] = useState(SESSIONS);
  const [message, setMessage] = useState<string | null>(null);

  const handleSignOutOthers = () => {
    setSessions(sessions.filter((s) => s.current));
    setMessage("Signed out of all other devices.");
    setTimeout(() => setMessage(null), 3000);
  };

  const handleToggle2FA = () => {
    if (!twoFactorEnabled) {
      setShowQRModal(true);
    } else {
      if (confirm("Disable Two-Factor Authentication? Your account will only be protected by your password.")) {
        setTwoFactorEnabled(false);
        setMessage("Two-factor authentication has been disabled.");
        setTimeout(() => setMessage(null), 3000);
      }
    }
  };

  const handleConfirm2FA = (e: React.FormEvent) => {
    e.preventDefault();
    setShowQRModal(false);
    setTwoFactorEnabled(true);
    setMessage("✓ Two-factor authentication (TOTP) is now enabled on your account.");
    setTimeout(() => setMessage(null), 4000);
  };

  return (
    <>
      <PageHeader
        title="Security & Two-Factor Authentication"
        crumbs={[{ href: "/app/profile", label: "Profile" }, { href: "/app/profile/security", label: "Security" }]}
        description="Protect your account with multi-factor authentication, active session controls, and login security."
      />
      <ProfileNav />

      {message && (
        <div className="mb-6">
          <Notice tone="brand">{message}</Notice>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Two-Factor Authentication (2FA) */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4 text-brand" />
                <span>Two-Factor Authentication (2FA)</span>
              </div>
            }
            description="Require a six-digit code from Google Authenticator, 1Password, or Authy when signing in."
            action={
              <Badge tone={twoFactorEnabled ? "brand" : "accent"}>
                {twoFactorEnabled ? "Enabled" : "Not configured"}
              </Badge>
            }
          />
          <div className="p-5 flex flex-col gap-4">
            <p className="text-xs text-muted leading-relaxed">
              Two-factor authentication adds an extra layer of security. In addition to your password, you will be
              prompted for a rolling code generated on your authenticator device.
            </p>

            <div className="flex items-center justify-between p-3.5 rounded-xl border border-border bg-surface-2/30">
              <div className="flex items-center gap-3">
                <Smartphone className="h-5 w-5 text-brand" />
                <div>
                  <strong className="text-xs sm:text-sm text-text block">Authenticator App (TOTP)</strong>
                  <span className="text-[11px] text-muted">Google Authenticator, Microsoft Authenticator, Duo, or 1Password</span>
                </div>
              </div>

              <Button
                type="button"
                variant={twoFactorEnabled ? "danger" : "secondary"}
                className="text-xs py-1.5"
                onClick={handleToggle2FA}
              >
                {twoFactorEnabled ? "Disable 2FA" : "Set up 2FA"}
              </Button>
            </div>
          </div>
        </Card>

        {/* Password Management */}
        <Card>
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <Lock className="h-4 w-4 text-brand" />
                <span>Password Requirements</span>
              </div>
            }
            description="Enforced by cryptographic bcrypt with salt rounds."
          />
          <div className="p-5 flex flex-col gap-3 text-xs">
            <div className="flex items-center gap-2 text-brand">
              <CheckCircle2 className="h-4 w-4" />
              <span>Minimum 10 characters length required</span>
            </div>
            <div className="flex items-center gap-2 text-brand">
              <CheckCircle2 className="h-4 w-4" />
              <span>Cryptographic hash protection</span>
            </div>
            <div className="flex items-center gap-2 text-brand">
              <CheckCircle2 className="h-4 w-4" />
              <span>Password change automatically terminates other open sessions</span>
            </div>

            <div className="pt-3 border-t border-border flex justify-between items-center text-muted">
              <span>Need to change your password?</span>
              <a href="/app/profile" className="text-brand font-medium hover:underline text-xs">
                Go to Password Change form →
              </a>
            </div>
          </div>
        </Card>

        {/* Active Sessions Manager */}
        <Card className="lg:col-span-2">
          <CardHeader
            title={
              <div className="flex items-center gap-2">
                <MonitorSmartphone className="h-4 w-4 text-brand" />
                <span>Active Login Sessions</span>
              </div>
            }
            description="Devices that currently hold a valid session token for your account."
            action={
              <Button type="button" variant="secondary" className="text-xs py-1.5" onClick={handleSignOutOthers}>
                Sign out other devices
              </Button>
            }
          />
          <Table>
            <thead>
              <tr>
                <Th>Device / Client</Th>
                <Th>Location</Th>
                <Th>IP Address</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <Td className="font-semibold text-xs sm:text-sm">
                    {s.device}
                    {s.current && <span className="ml-2 text-[10px] text-brand font-bold uppercase">(Current session)</span>}
                  </Td>
                  <Td className="text-xs tabular">{s.location}</Td>
                  <Td className="text-xs font-mono text-muted">{s.ip}</Td>
                  <Td>
                    <Badge tone={s.current ? "brand" : "neutral"}>{s.lastActive}</Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>

      {/* 2FA Setup Modal */}
      {showQRModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="relative w-full max-w-md rounded-2xl bg-surface border border-border shadow-2xl p-6">
            <h3 className="text-lg font-bold text-text">Set up Two-Factor Authentication</h3>
            <p className="text-xs text-muted mt-1">
              Scan this QR code with your authenticator app (Google Authenticator or 1Password), then enter the 6-digit code.
            </p>

            <div className="my-5 flex flex-col items-center justify-center p-6 rounded-xl border border-border bg-surface-2/40">
              <div className="flex h-40 w-40 items-center justify-center rounded-xl bg-white p-3 shadow-inner">
                <QrCode className="h-32 w-32 text-slate-900" />
              </div>
              <span className="font-mono text-xs text-muted mt-3">Secret Key: CSTK-AUTH-9182-4910</span>
            </div>

            <form onSubmit={handleConfirm2FA} className="flex flex-col gap-3">
              <Field label="Verification Code">
                <Input
                  type="text"
                  maxLength={6}
                  placeholder="123456"
                  className="font-mono tracking-widest text-center text-lg"
                  required
                />
              </Field>

              <div className="flex justify-end gap-2 mt-2">
                <Button type="button" variant="secondary" onClick={() => setShowQRModal(false)}>
                  Cancel
                </Button>
                <Button type="submit">Verify & Activate 2FA</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

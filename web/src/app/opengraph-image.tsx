import { ImageResponse } from "next/og";

export const alt = "Carbonstack · Digital MRV & Carbon Credit Operating System";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "space-between",
          backgroundColor: "#0f1411",
          backgroundImage: "radial-gradient(circle at 25px 25px, rgba(31, 122, 77, 0.15) 2%, transparent 0%)",
          backgroundSize: "50px 50px",
          padding: "60px 80px",
          fontFamily: "system-ui, -apple-system, sans-serif",
          color: "#ffffff",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "14px",
              backgroundColor: "#1f7a4d",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 30px rgba(31, 122, 77, 0.5)",
            }}
          >
            <svg viewBox="0 0 32 32" width="36" height="36" fill="none">
              <path
                d="M9 21c0-6 4-10 13-11-1 8-5 12-11 12"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
              <path d="M9 23l6-6" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </div>
          <span style={{ fontSize: "36px", fontWeight: 700, letterSpacing: "-0.03em" }}>
            Carbonstack
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "950px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              backgroundColor: "rgba(31, 122, 77, 0.2)",
              border: "1px solid rgba(31, 122, 77, 0.4)",
              borderRadius: "999px",
              padding: "6px 16px",
            }}
          >
            <span style={{ fontSize: "14px", color: "#49b07a", fontWeight: 600, letterSpacing: "0.05em" }}>
              PRECISION dMRV PLATFORM · ARTICLE 6 COMPLIANT
            </span>
          </div>
          <h1
            style={{
              fontSize: "56px",
              fontWeight: 800,
              lineHeight: 1.15,
              letterSpacing: "-0.03em",
              margin: 0,
              color: "#e7ece8",
            }}
          >
            Quantify carbon credits from satellite data, down to the meter.
          </h1>
          <p
            style={{
              fontSize: "22px",
              color: "#97a59b",
              lineHeight: 1.4,
              margin: 0,
            }}
          >
            Enrol farms, monitor practices via radar, quantify GHG abatement, and settle transparent farmer payouts.
          </p>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
            borderTop: "1px solid rgba(255, 255, 255, 0.1)",
            paddingTop: "24px",
          }}
        >
          <div style={{ display: "flex", gap: "28px", color: "#97a59b", fontSize: "16px", fontWeight: 500 }}>
            <span>• Verra VM0051 & VM0047</span>
            <span>• Sentinel-1 Radar Water Telemetry</span>
            <span>• Traceable Serial Ledger</span>
          </div>
          <span style={{ color: "#49b07a", fontSize: "16px", fontWeight: 600 }}>
            carbonstack.io
          </span>
        </div>
      </div>
    ),
    { ...size }
  );
}

const COLOR = { up: "#16a34a", degraded: "#d97706", down: "#dc2626" };

function barColor(u) {
  if (u >= 0.995) return COLOR.up;
  if (u >= 0.9) return COLOR.degraded;
  return COLOR.down;
}

/** 90-day availability bar strip. `data`: [{ day, uptime }] with uptime in 0..1. */
export default function UptimeBars({ data, height = 34 }) {
  if (!data?.length) return <div className="muted" style={{ fontSize: 13 }}>No availability data</div>;
  return (
    <div>
      <div style={{ display: "flex", gap: 2, height, alignItems: "stretch" }}>
        {data.map((d, i) => (
          <div
            key={i}
            title={`${new Date(d.day).toLocaleDateString()} — ${(d.uptime * 100).toFixed(2)}% uptime`}
            style={{
              flex: 1,
              minWidth: 2,
              borderRadius: 2,
              background: barColor(d.uptime),
              opacity: 0.85,
            }}
          />
        ))}
      </div>
      <div className="spread" style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>
        <span>90 days ago</span>
        <span>Today</span>
      </div>
    </div>
  );
}

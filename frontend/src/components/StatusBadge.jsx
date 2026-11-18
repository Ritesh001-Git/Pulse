const LABELS = { up: "Operational", degraded: "Degraded", down: "Down", maintenance: "Maintenance", unknown: "Unknown" };

export default function StatusBadge({ status, size }) {
  return (
    <span className={`badge badge--${status || "unknown"}`} style={size ? { fontSize: size } : undefined}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: "currentColor" }} />
      {LABELS[status] || status}
    </span>
  );
}

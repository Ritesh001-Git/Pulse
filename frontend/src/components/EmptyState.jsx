export default function EmptyState({ icon = "📭", title, hint }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 24px" }}>
      <div style={{ fontSize: 32, marginBottom: 10 }}>{icon}</div>
      <div style={{ fontWeight: 600 }}>{title}</div>
      {hint && <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

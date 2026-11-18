export default function StatCard({ label, value, hint, accent }) {
  return (
    <div className="stat-card">
      <div className="stat-card__label">
        {accent && <span style={{ width: 8, height: 8, borderRadius: "50%", background: accent }} />}
        {label}
      </div>
      <div className="stat-card__value">{value}</div>
      {hint && <div className="stat-card__hint">{hint}</div>}
    </div>
  );
}

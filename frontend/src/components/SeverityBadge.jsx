const STYLES = {
  outage: "badge--down",
  degradation: "badge--degraded",
};

const LABELS = { outage: "Outage", degradation: "Degradation" };

export default function SeverityBadge({ severity }) {
  return <span className={`badge ${STYLES[severity] || "badge--neutral"}`}>{LABELS[severity] || severity}</span>;
}

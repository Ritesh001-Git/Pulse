const STATE_STYLES = {
  investigating: "badge--down",
  identified: "badge--degraded",
  monitoring: "badge--maintenance",
  resolved: "badge--up",
};

const LABELS = {
  investigating: "Investigating",
  identified: "Identified",
  monitoring: "Monitoring",
  resolved: "Resolved",
};

export default function IncidentStateBadge({ state }) {
  return <span className={`badge ${STATE_STYLES[state] || "badge--neutral"}`}>{LABELS[state] || state}</span>;
}

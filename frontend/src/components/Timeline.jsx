const DOT_KIND = {
  auto_detected: "timeline-dot--down",
  status_changed: "timeline-dot--note",
  acked: "timeline-dot--note",
  resolved: "timeline-dot--up",
};

function fmt(at) {
  return new Date(at).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Incident timeline. Events: [{ at, actor: "system"|"user", who?, kind, message }]
 */
export default function Timeline({ events }) {
  if (!events?.length) return <div className="muted" style={{ fontSize: 13 }}>No events yet.</div>;
  return (
    <div className="timeline">
      {events.map((e, i) => (
        <div className="timeline-item" key={i}>
          <span className={`timeline-dot ${DOT_KIND[e.kind] || "timeline-dot--degraded"}`} />
          <div className="timeline-meta">
            <span>{fmt(e.at)}</span>
            <span className={`timeline-actor ${e.actor === "user" ? "timeline-actor--user" : ""}`}>
              {e.actor === "user" ? e.who || "Engineer" : "Pulse"}
            </span>
          </div>
          <div style={{ fontSize: 13 }}>{e.message}</div>
        </div>
      ))}
    </div>
  );
}

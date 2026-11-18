import { useNavigate, Link } from "react-router-dom";
import PageHeader from "../components/PageHeader.jsx";
import StatCard from "../components/StatCard.jsx";
import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import IncidentStateBadge from "../components/IncidentStateBadge.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";
import PageState from "../components/PageState.jsx";
import { useApi } from "../api/hooks.js";
import { listServices, listIncidents, getSlo } from "../api/client.js";
import { formatRelative } from "../utils/format.js";

const COLORS = { up: "#16a34a", degraded: "#d97706", down: "#dc2626" };

export default function Overview() {
  const servicesQuery = useApi(listServices);
  const incidentsQuery = useApi(listIncidents);
  const sloQuery = useApi(getSlo, "30d", { staleTime: 60_000 });
  const navigate = useNavigate();

  const isPending = servicesQuery.isPending || incidentsQuery.isPending || sloQuery.isPending;
  const isError = servicesQuery.isError || incidentsQuery.isError || sloQuery.isError;
  const error = servicesQuery.error ?? incidentsQuery.error ?? sloQuery.error;

  const services = servicesQuery.data ?? [];
  const incidents = incidentsQuery.data ?? [];
  const slo = (sloQuery.data ?? []).filter((s) => !s.compliant);
  const summary = {
    total: services.length,
    up: services.filter((s) => s.status === "up").length,
    degraded: services.filter((s) => s.status === "degraded").length,
    down: services.filter((s) => s.status === "down").length,
    activeIncidents: incidents.filter((i) => i.state !== "resolved").length,
  };
  const activeIncidents = incidents.filter((i) => i.state !== "resolved");

  return (
    <>
      <PageHeader title="Overview" subtitle="Real-time health across all monitored services" />

      <PageState isPending={isPending} isError={isError} error={error}
        onRetry={() => { servicesQuery.refetch(); incidentsQuery.refetch(); }}
        skeletons={2} minHeight={140}>
        <>
          <div className="stats-grid">
            <StatCard label="Total services" value={summary.total} hint="actively monitored" />
            <StatCard label="Operational" value={summary.up} accent={COLORS.up} />
            <StatCard label="Degraded" value={summary.degraded} accent={COLORS.degraded} />
            <StatCard label="Down" value={summary.down} accent={COLORS.down} />
            <StatCard label="Active incidents" value={summary.activeIncidents} hint="open or unresolved" />
          </div>

          <div className="detail-grid">
            <Card
              title="Service health"
              actions={<a href="/services" className="muted" style={{ fontSize: 13 }}>View all →</a>}
            >
              <table className="table table--clickable">
                <tbody>
                  {services.map((s) => (
                    <tr key={s.id} onClick={() => navigate(`/services/${s.id}`)}>
                      <td style={{ width: "55%" }}>
                        <span style={{ fontWeight: 600 }}>{s.name}</span>
                        <div className="muted" style={{ fontSize: 12 }}>{s.url}</div>
                      </td>
                      <td><StatusBadge status={s.status} /></td>
                      <td className="muted" style={{ textAlign: "right", fontSize: 12 }}>
                        {s.status === "down" ? "—" : `${s.responseTimeMs} ms`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title={`Active incidents (${activeIncidents.length})`}>
              {activeIncidents.length === 0 ? (
                <div className="card__body muted" style={{ fontSize: 13 }}>
                  No active incidents. All clear. ✅
                </div>
              ) : (
                activeIncidents.map((inc) => (
                  <div key={inc.id}
                    onClick={() => navigate(`/incidents/${inc.id}`)}
                    className="service-row" style={{ cursor: "pointer" }}>
                    <div className="spread">
                      <strong style={{ fontSize: 13 }}>{inc.serviceName}</strong>
                      <SeverityBadge severity={inc.severity} />
                    </div>
                    <div style={{ fontSize: 13, margin: "4px 0 6px" }}>{inc.title}</div>
                    <div className="row spread">
                      <IncidentStateBadge state={inc.state} />
                      <span className="muted" style={{ fontSize: 12 }}>
                        opened {formatRelative(inc.openedAt)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </Card>
          </div>

          <Card title={`SLO / error budgets (30d)${slo.length ? ` — ${slo.length} breached` : ""}`}>
            <table className="table">
              <thead>
                <tr className="muted" style={{ fontSize: 12 }}>
                  <th>SERVICE</th><th>UPTIME</th><th>SLO</th><th>BUDGET REMAINING</th><th>STATUS</th>
                </tr>
              </thead>
              <tbody>
                {(sloQuery.data ?? []).map((s) => (
                  <tr key={s.serviceId} onClick={() => navigate(`/services/${s.serviceId}`)}
                    className="table--clickable" style={{ cursor: "pointer" }}>
                    <td style={{ fontWeight: 600 }}>{s.serviceName}</td>
                    <td>{s.uptimePct.toFixed(2)}%</td>
                    <td className="muted">{s.slaTarget}%</td>
                    <td>
                      {s.budgetRemainingPct === null ? "—" : `${s.budgetRemainingPct}%`}
                      <div style={{ background: "var(--border)", height: 4, borderRadius: 2, marginTop: 3, maxWidth: 140 }}>
                        <div style={{
                          width: `${Math.max(0, Math.min(100, s.budgetRemainingPct ?? 0))}%`,
                          height: "100%", borderRadius: 2,
                          background: (s.budgetRemainingPct ?? 100) < 25 ? "#dc2626" : (s.budgetRemainingPct ?? 100) < 60 ? "#d97706" : "#16a34a",
                        }} />
                      </div>
                    </td>
                    <td>
                      <span className="badge" style={s.compliant
                        ? { background: "rgba(22,163,74,.12)", color: "#16a34a" }
                        : { background: "rgba(220,38,38,.12)", color: "#dc2626" }}>
                        {s.compliant ? "within budget" : "budget breached"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      </PageState>
    </>
  );
}

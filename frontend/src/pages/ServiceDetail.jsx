import { useParams } from "react-router-dom";
import { useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import Card from "../components/Card.jsx";
import StatCard from "../components/StatCard.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";
import IncidentStateBadge from "../components/IncidentStateBadge.jsx";
import LatencyChart from "../components/LatencyChart.jsx";
import UptimeBars from "../components/UptimeBars.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageState from "../components/PageState.jsx";
import EditServiceModal from "../components/EditServiceModal.jsx";
import { useApi, useRunCheck } from "../api/hooks.js";
import { getService, listIncidents } from "../api/client.js";
import { formatDateTime, formatDuration } from "../utils/format.js";

function avgLatency(data) {
  if (!data?.length) return "—";
  return `${Math.round(data.reduce((a, b) => a + b.ms, 0) / data.length)} ms`;
}

export default function ServiceDetail() {
  const { id } = useParams();
  const { data: service, isPending, isError, error, refetch } = useApi(getService, id);
  const { data: incidents = [] } = useApi(listIncidents);
  const runCheck = useRunCheck(id);
  const [checkResult, setCheckResult] = useState(null);
  const [showEdit, setShowEdit] = useState(false);

  const handleRunCheck = async () => {
    setCheckResult(null);
    const res = await runCheck.mutateAsync();
    setCheckResult(res);
    refetch();
  };

  if (isPending || isError) {
    return (
      <>
        <PageHeader title="Service" backTo="/services" backLabel="Back to services" />
        <PageState isPending={isPending} isError={isError} error={error} onRetry={refetch} skeletons={4} />
      </>
    );
  }

  if (!service) {
    return (
      <>
        <PageHeader title="Service not found" backTo="/services" backLabel="Back to services" />
        <Card><EmptyState icon="🔍" title="Unknown service" hint="It may have been removed." /></Card>
      </>
    );
  }

  const related = incidents.filter((i) => i.serviceId === service.id);

  return (
    <>
      <PageHeader
        title={service.name}
        subtitle={`${service.description ?? "No description"} · ${service.url}${service.healthPath} · checked every ${service.checkIntervalSec}s`}
        backTo="/services"
        backLabel="Back to services"
      >
        <StatusBadge status={service.status} />
        <button className="btn" onClick={handleRunCheck} disabled={runCheck.isPending}>
          {runCheck.isPending ? "Checking…" : "Run check now"}
        </button>
        <button className="btn" onClick={() => setShowEdit(true)}>Edit</button>
      </PageHeader>

      {showEdit && <EditServiceModal service={service} onClose={() => setShowEdit(false)} />}

      {checkResult && (
        <div
          className="badge"
          style={{
            width: "fit-content", marginBottom: 12,
            background: checkResult.check.status === "up" ? "rgba(22,163,74,.12)" : checkResult.check.status === "degraded" ? "rgba(217,119,6,.12)" : "rgba(220,38,38,.12)",
            color: checkResult.check.status === "up" ? "#16a34a" : checkResult.check.status === "degraded" ? "#d97706" : "#dc2626",
          }}
        >
          {checkResult.check.status === "up" ? "✅" : checkResult.check.status === "degraded" ? "⚠️" : "❌"}{" "}
          Check: {checkResult.check.status} in {checkResult.check.latencyMs ?? "—"}ms · state {checkResult.serviceState}
          {checkResult.stateChanged ? " (changed)" : ""}
        </div>
      )}
      {runCheck.isError && (
        <div className="badge badge--down" style={{ width: "fit-content", marginBottom: 12 }}>
          Check failed: {runCheck.error?.message}
        </div>
      )}

      <div className="stats-grid">
        <StatCard label="Current status" value={{ healthy: "Healthy", degraded: "Degraded", down: "Down", pending: "Pending" }[service.serviceState] ?? service.serviceState} hint={service.serviceState} />
        <StatCard label="Response time" value={service.status === "down" ? "—" : `${service.responseTimeMs} ms`} hint="latest check" />
        <StatCard label="Availability (30d)" value={`${service.availability?.toFixed(2)}%`} hint={`SLA target ${service.slaTarget}%`} />
        <StatCard label="Avg latency (24h)" value={avgLatency(service.latency)} hint="rolling average" />
        <StatCard label="Owner" value={service.owner} hint={service.url} />
      </div>

      <div className="stack">
        <Card title="Response time (last 24 hours)">
          <div className="card__body">
            <LatencyChart data={service.latency ?? []} />
          </div>
        </Card>

        <Card
          title="Uptime & reliability"
          actions={<span className="muted" style={{ fontSize: 12 }}>Reliability target: {service.slaTarget}% monthly</span>}
        >
          <div className="card__body">
            <UptimeBars data={service.uptime ?? []} />
            <div className="row" style={{ marginTop: 14, fontSize: 12 }}>
              <span className="row"><span style={{ width: 10, height: 10, borderRadius: 2, background: "#16a34a" }} /> ≥ 99.5%</span>
              <span className="row"><span style={{ width: 10, height: 10, borderRadius: 2, background: "#d97706" }} /> 90–99.5%</span>
              <span className="row"><span style={{ width: 10, height: 10, borderRadius: 2, background: "#dc2626" }} /> &lt; 90%</span>
            </div>
          </div>
        </Card>

        <Card title={`Recent incidents (${related.length})`}>
          {related.length === 0 ? (
            <EmptyState icon="✅" title="No incidents" hint="This service has had no reported incidents." />
          ) : (
            related.map((inc) => (
              <a key={inc.id} href={`/incidents/${inc.id}`} className="service-row">
                <div style={{ maxWidth: "70%" }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{inc.title}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {formatDateTime(inc.openedAt)} ·{" "}
                    {inc.resolvedAt ? `resolved in ${formatDuration(inc.openedAt, inc.resolvedAt)}` : "ongoing"}
                  </div>
                </div>
                <div className="row">
                  <SeverityBadge severity={inc.severity} />
                  <IncidentStateBadge state={inc.state} />
                </div>
              </a>
            ))
          )}
        </Card>
      </div>
    </>
  );
}

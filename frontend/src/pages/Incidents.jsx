import { useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader.jsx";
import Card from "../components/Card.jsx";
import Table from "../components/Table.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";
import IncidentStateBadge from "../components/IncidentStateBadge.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageState from "../components/PageState.jsx";
import FileIncidentModal from "../components/FileIncidentModal.jsx";
import { useApi } from "../api/hooks.js";
import { listIncidents, listServices } from "../api/client.js";
import { formatDateTime, formatDuration } from "../utils/format.js";

export default function Incidents() {
  const { data: incidents = [], isPending, isError, error, refetch } = useApi(listIncidents);
  const { data: services = [] } = useApi(listServices, null, { staleTime: 30_000 });
  const navigate = useNavigate();
  const [showFile, setShowFile] = useState(false);

  const active = incidents.filter((i) => i.state !== "resolved");
  const past = incidents.filter((i) => i.state === "resolved");

  const columns = [
    {
      key: "title",
      label: "Incident",
      render: (i) => (
        <div>
          <div style={{ fontWeight: 600 }}>{i.title}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {i.serviceName} · opened {formatDateTime(i.openedAt)}
          </div>
        </div>
      ),
    },
    { key: "severity", label: "Severity", render: (i) => <SeverityBadge severity={i.severity} /> },
    { key: "state", label: "Status", render: (i) => <IncidentStateBadge state={i.state} /> },
    {
      key: "ack",
      label: "Acknowledged",
      render: (i) =>
        i.acknowledged ? (
          <span className="muted" style={{ fontSize: 12 }}>by {i.ackedBy}</span>
        ) : (
          <span className="badge badge--down">Unacknowledged</span>
        ),
    },
    {
      key: "duration",
      label: "Duration",
      render: (i) => <span className="mono">{formatDuration(i.openedAt, i.resolvedAt)}</span>,
    },
  ];

  return (
    <>
      <PageHeader title="Incidents" subtitle="Current and historical incidents across all services">
        <button className="btn btn-primary" onClick={() => setShowFile(true)}>+ File incident</button>
      </PageHeader>

      {showFile && (
        <FileIncidentModal services={services} onClose={() => setShowFile(false)} onCreated={() => refetch()} />
      )}

      <PageState isPending={isPending} isError={isError} error={error} onRetry={refetch} skeletons={4}>
        <div className="stack">
          <Card title={`Active incidents (${active.length})`}>
            <Table
              columns={columns}
              rows={active}
              rowKey={(i) => i.id}
              onRowClick={(i) => navigate(`/incidents/${i.id}`)}
              empty={<EmptyState icon="✅" title="No active incidents" hint="Every service is behaving normally." />}
            />
          </Card>

          <Card title={`Past incidents (${past.length})`}>
            <Table
              columns={columns}
              rows={past}
              rowKey={(i) => i.id}
              onRowClick={(i) => navigate(`/incidents/${i.id}`)}
              empty={<EmptyState title="No past incidents" />}
            />
          </Card>
        </div>
      </PageState>
    </>
  );
}

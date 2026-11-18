import { useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader.jsx";
import Card from "../components/Card.jsx";
import Table from "../components/Table.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageState from "../components/PageState.jsx";
import RegisterServiceModal from "../components/RegisterServiceModal.jsx";
import { useApi } from "../api/hooks.js";
import { listServices } from "../api/client.js";
import { formatRelative } from "../utils/format.js";

export default function Services() {
  const { data: services = [], isPending, isError, error, refetch } = useApi(listServices);
  const navigate = useNavigate();
  const [showRegister, setShowRegister] = useState(false);

  const columns = [
    {
      key: "name",
      label: "Service",
      render: (s) => (
        <div>
          <div style={{ fontWeight: 600 }}>{s.name}</div>
          <div className="muted" style={{ fontSize: 12 }}>{s.description}</div>
        </div>
      ),
    },
    { key: "owner", label: "Owner", render: (s) => <span className="badge badge--outline">{s.owner ?? "—"}</span> },
    { key: "status", label: "Status", render: (s) => <StatusBadge status={s.status} /> },
    {
      key: "rt",
      label: "Response time",
      render: (s) => (s.status === "down" ? <span className="muted">—</span> : <span className="mono">{s.responseTimeMs} ms</span>),
    },
    {
      key: "avail",
      label: "Availability (30d)",
      render: (s) => (
        <span style={{ fontWeight: 600, color: s.availability >= s.slaTarget ? "var(--up)" : "var(--degraded)" }}>
          {s.availability?.toFixed(2)}%
        </span>
      ),
    },
    { key: "last", label: "Last check", render: (s) => <span className="muted" style={{ fontSize: 12 }}>{formatRelative(s.lastCheckedAt)}</span> },
  ];

  return (
    <>
      <PageHeader title="Services" subtitle="Monitored endpoints, owners and current health">
        <button className="btn btn-primary" onClick={() => setShowRegister(true)}>+ Register service</button>
      </PageHeader>

      {showRegister && (
        <RegisterServiceModal
          onClose={() => setShowRegister(false)}
          onCreated={() => refetch()}
        />
      )}

      <PageState isPending={isPending} isError={isError} error={error} onRetry={refetch} skeletons={3}>
        <Card>
          <Table
            columns={columns}
            rows={services}
            rowKey={(s) => s.id}
            onRowClick={(s) => navigate(`/services/${s.id}`)}
            empty={<EmptyState title="No services yet" hint="Register your first service to start monitoring." />}
          />
        </Card>
      </PageState>
    </>
  );
}

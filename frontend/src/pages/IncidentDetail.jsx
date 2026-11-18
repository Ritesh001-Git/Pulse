import { useParams } from "react-router-dom";
import PageHeader from "../components/PageHeader.jsx";
import Card from "../components/Card.jsx";
import StatCard from "../components/StatCard.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";
import IncidentStateBadge from "../components/IncidentStateBadge.jsx";
import Timeline from "../components/Timeline.jsx";
import NotesSection from "../components/NotesSection.jsx";
import EmptyState from "../components/EmptyState.jsx";
import PageState from "../components/PageState.jsx";
import { useIncident, useAckIncident, useAddIncidentNote, useResolveIncident, useApi } from "../api/hooks.js";
import { listServices } from "../api/client.js";
import { formatDateTime, formatDuration } from "../utils/format.js";

export default function IncidentDetail() {
  const { id } = useParams();
  const { data: incident, isPending, isError, error, refetch } = useIncident(id);
  const { data: services = [] } = useApi(listServices);

  const ackMutation = useAckIncident(id);
  const noteMutation = useAddIncidentNote(id);
  const resolveMutation = useResolveIncident(id);

  if (isPending || isError) {
    return (
      <>
        <PageHeader title="Incident" backTo="/incidents" backLabel="Back to incidents" />
        <PageState isPending={isPending} isError={isError} error={error} onRetry={refetch} skeletons={4} />
      </>
    );
  }

  if (!incident) {
    return (
      <>
        <PageHeader title="Incident not found" backTo="/incidents" backLabel="Back to incidents" />
        <Card><EmptyState icon="🔍" title="Unknown incident" /></Card>
      </>
    );
  }

  const service = services.find((s) => s.id === incident.serviceId);
  const acked = incident.acknowledged;
  const isBusy = ackMutation.isPending || noteMutation.isPending || resolveMutation.isPending;

  // Ack + note + resolve all flow through TanStack Query mutations.
  // Each updates the detail cache and invalidates lists, so the timeline,
  // incident table and overview stay consistent without manual state sync.
  const acknowledge = () => ackMutation.mutate({ id });
  const addNote = (body) => noteMutation.mutate({ id, body });
  const resolve = () => resolveMutation.mutate({ id });

  return (
    <>
      <PageHeader
        title={incident.title}
        subtitle={`${incident.serviceName} · opened ${formatDateTime(incident.openedAt)}`}
        backTo="/incidents"
        backLabel="Back to incidents"
      >
        <SeverityBadge severity={incident.severity} />
        <IncidentStateBadge state={incident.state} />
      </PageHeader>

      <div className="stats-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}>
        <StatCard label="Service" value={service?.name ?? incident.serviceName} hint={service?.url} />
        <StatCard label="Duration" value={formatDuration(incident.openedAt, incident.resolvedAt)} hint={incident.resolvedAt ? "resolved" : "ongoing"} />
        <StatCard
          label="Acknowledgement"
          value={acked ? "Acknowledged" : "Pending"}
          hint={acked ? incident.ackedBy ?? "—" : "no one has acked yet"}
        />
      </div>

      <div className="detail-grid">
        <div className="stack">
          <Card title="Timeline">
            <div className="card__body">
              <Timeline events={incident.timeline} />
            </div>
          </Card>

          <Card title="Notes">
            <div className="card__body">
              <NotesSection
                notes={incident.notes ?? []}
                onAdd={addNote}
                busy={noteMutation.isPending}
                error={noteMutation.error?.message}
              />
            </div>
          </Card>
        </div>

        <div className="stack">
          <Card title="Actions">
            <div className="card__body stack" style={{ gap: 10 }}>
              {ackMutation.isError && <div className="badge badge--down">Ack failed: {ackMutation.error.message}</div>}
              {resolveMutation.isError && <div className="badge badge--down">Resolve failed: {resolveMutation.error.message}</div>}
              <button className="btn btn-primary" onClick={acknowledge} disabled={acked || isBusy}>
                {acked ? "✓ Acknowledged" : ackMutation.isPending ? "Acknowledging…" : "Acknowledge incident"}
              </button>
              <button className="btn">Post status update</button>
              <button className="btn btn-success" onClick={resolve}
                disabled={incident.state === "resolved" || isBusy}>
                {resolveMutation.isPending ? "Resolving…" : "Resolve incident"}
              </button>
            </div>
          </Card>

          <Card title="Customer communication">
            <div
              className="status-message"
              style={
                incident.state !== "resolved"
                  ? { background: "var(--degraded-soft)", color: "var(--degraded)", borderColor: "#f0d9a8" }
                  : {}
              }
            >
              {incident.state === "resolved"
                ? "This incident has been resolved. The public status page shows the service as operational."
                : `We are aware of a problem with ${incident.serviceName} and are actively investigating. Customers see this message on the public status page.`}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

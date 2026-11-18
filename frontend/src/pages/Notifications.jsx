import PageHeader from "../components/PageHeader.jsx";
import PageState from "../components/PageState.jsx";
import Card from "../components/Card.jsx";
import { useApi } from "../api/hooks.js";
import { getDeliveries } from "../api/client.js";
import { formatRelative } from "../utils/format.js";

const STATUS_STYLE = {
  sent: { background: "rgba(22,163,74,.12)", color: "#16a34a" },
  pending: { background: "rgba(217,119,6,.12)", color: "#d97706" },
  failed: { background: "rgba(220,38,38,.12)", color: "#dc2626" },
};

export default function Notifications() {
  const q = useApi(getDeliveries);

  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle="Webhook delivery history — every incident event fanned out per channel"
      />
      <PageState isPending={q.isPending} isError={q.isError} error={q.error} onRetry={q.refetch} skeletons={3} minHeight={240}>
        <Card title={`Delivery history (${(q.data ?? []).length})`}>
          <table className="table">
            <thead>
              <tr className="muted" style={{ fontSize: 12 }}>
                <th>WHEN</th><th>EVENT</th><th>CHANNEL</th><th>STATUS</th><th>DETAIL</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((d) => (
                <tr key={d.id}>
                  <td className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{formatRelative(d.createdAt)}</td>
                  <td style={{ fontWeight: 600, fontSize: 13 }}>{d.event ?? "—"}</td>
                  <td style={{ fontSize: 13 }}>{d.audience}</td>
                  <td>
                    <span className="badge" style={STATUS_STYLE[d.status] ?? {}}>{d.status}</span>
                  </td>
                  <td className="muted" style={{ fontSize: 12, maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {d.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </PageState>
    </>
  );
}

import PageHeader from "../components/PageHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import UptimeBars from "../components/UptimeBars.jsx";
import PageState from "../components/PageState.jsx";
import { useApi } from "../api/hooks.js";
import { getPublicStatus, getService } from "../api/client.js";

const BANNER = {
  up: { cls: "status-banner--up", icon: "✅", text: "All systems operational" },
  degraded: { cls: "status-banner--degraded", icon: "⚠️", text: "Some systems are experiencing degradation" },
  down: { cls: "status-banner--down", icon: "🛑", text: "Some systems are experiencing an outage" },
};

function bannerFor(overall, counts) {
  // Server sends `overall`, but guard against it missing until backend lands.
  if (overall) return BANNER[overall];
  if (counts?.down > 0) return BANNER.down;
  if (counts?.degraded > 0) return BANNER.degraded;
  return BANNER.up;
}

export default function PublicStatus() {
  const { data, isPending, isError, error, refetch } = useApi(getPublicStatus, null, {
    refetchInterval: 30_000, // live-ish updates until WS lands
  });
  const services = data?.services ?? [];
  const incidents = data?.incidents ?? [];

  // Pull 90-day uptime series per service (also proves per-id detail fetching works).
  const details = useDetails(services);

  return (
    <div className="status-page">
      <header className="spread">
        <div className="row" style={{ gap: 10 }}>
          <span className="sidebar__logo" style={{ color: "#fff" }}>P</span>
          <span style={{ fontSize: 17, fontWeight: 700 }}>Pulse Status</span>
        </div>
        <a href="/" className="muted" style={{ fontSize: 13 }}>← Internal dashboard</a>
      </header>

      <PageState isPending={isPending} isError={isError} error={error} onRetry={refetch} skeletons={5} minHeight={420}>
        <>
          {(() => {
            const banner = bannerFor(data?.overall, data?.counts);
            return (
              <div className={`status-banner ${banner.cls}`}>
                {banner.icon} {banner.text}
              </div>
            );
          })()}

          <div className="status-message" style={{ marginBottom: 20 }}>
            <strong>Experiencing an error?</strong> This page shows real-time health of our
            services. If every service shows <em>Operational</em>, the problem is most likely on
            your side — check your connection, API keys or integration. If a service here shows{" "}
            <em>Degraded</em> or <em>Down</em>, the issue is on our side and our engineers are
            already working on it.
          </div>

          <section className="card">
            {services.map((svc) => {
              const activeIncident = incidents.find((i) => i.serviceId === svc.id && i.state !== "resolved");
              const msg = svc.publicMessage ?? customerFallback(svc);
              return (
                <div key={svc.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <div className="service-row">
                    <div>
                      <div style={{ fontWeight: 600 }}>{svc.name}</div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {svc.status === "down" ? "Outage in progress" : `${svc.responseTimeMs ?? "—"} ms · ${svc.availability?.toFixed(2)}% uptime (30d)`}
                      </div>
                    </div>
                    <StatusBadge status={svc.status} />
                  </div>
                  {msg && (
                    <div className="status-message" style={{ margin: "0 20px 16px" }}>
                      <strong>Customer notice:</strong> {msg}
                    </div>
                  )}
                </div>
              );
            })}
          </section>

          <h2 style={{ margin: "32px 0 12px" }}>Uptime — last 90 days</h2>
          <section className="card" style={{ padding: 20, display: "grid", gap: 20 }}>
            {services.map((svc) => (
              <div key={svc.id}>
                <div className="spread" style={{ marginBottom: 8 }}>
                  <strong style={{ fontSize: 13 }}>{svc.name}</strong>
                  <span className="muted" style={{ fontSize: 12 }}>{svc.availability?.toFixed(2)}%</span>
                </div>
                <UptimeBars data={details[svc.id]?.uptime ?? []} height={28} />
              </div>
            ))}
          </section>

          <h2 style={{ margin: "32px 0 12px" }}>Past incidents</h2>
          <section className="card">
            {incidents.filter((i) => i.state === "resolved").length === 0 ? (
              <div className="card__body muted" style={{ fontSize: 13 }}>No incidents in the last 90 days.</div>
            ) : (
              incidents
                .filter((i) => i.state === "resolved")
                .map((i) => (
                  <div key={i.id} className="service-row" style={{ display: "block" }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>
                      {i.serviceName} — {i.title}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {new Date(i.openedAt).toLocaleString()} · resolved in {Math.round((i.resolvedAt - i.openedAt) / 60000)} min
                    </div>
                  </div>
                ))
            )}
          </section>

          <footer className="muted" style={{ textAlign: "center", fontSize: 12, marginTop: 40 }}>
            Powered by Pulse · Status refreshes automatically every 30 seconds.
          </footer>
        </>
      </PageState>
    </div>
  );
}

function customerFallback(svc) {
  if (svc.status === "down") {
    return `We are aware of an outage affecting ${svc.name}. Our team is actively working on it — we will post updates here as we make progress.`;
  }
  if (svc.status === "degraded") {
    return `${svc.name} is slower than normal. We have identified the cause and are working on a fix. No action is needed from you.`;
  }
  return null;
}

/** Fetch 90-day uptime per service (parallel, cached by TanStack Query). */
function useDetails(services) {
  const queries = useAllServiceDetails(services);
  return Object.fromEntries(queries.map((q, i) => [services[i]?.id, q.data]).filter(([, d]) => d));
}

// Implemented as a tiny wrapper so the hooks loop stays rule-compliant.
import { useQueries } from "@tanstack/react-query";
import * as api from "../api/client.js";
function useAllServiceDetails(services) {
  return useQueries({
    queries: services.map((s) => ({
      queryKey: ["getService", s.id],
      queryFn: () => api.getService(s.id),
    })),
  });
}

/**
 * HTTP client — the single seam between the UI and the Pulse backend.
 * Adds the bearer token from localStorage; on 401 clears the session and
 * redirects to /login (except on the login call itself).
 */
const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("pulse_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...options.headers },
    ...options,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    localStorage.removeItem("pulse_token");
    localStorage.removeItem("pulse_user");
    if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/status")) {
      window.location.assign("/login");
    }
    const err = new Error("Session expired");
    err.status = 401;
    throw err;
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* keep statusText */ }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ---------------- Auth ---------------- */

export const login = (email, password) =>
  request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });

/* ---------------- Queries ---------------- */

export const listServices = () => request("/api/services");
export const getService = (id) => request(`/api/services/${id}`);
export const listIncidents = () => request("/api/incidents");
export const getIncident = (id) => request(`/api/incidents/${id}`);
export const getPublicStatus = () => request("/api/public/status");
export const getSlo = (window = "30d") => request(`/api/metrics/slo?window=${window}`);
export const getMetricsIncidents = (window = "30d") => request(`/api/metrics/incidents?window=${window}`);
export const getDeliveries = () => request("/api/channels/deliveries");
export const listChannels = () => request("/api/channels");
export const createChannel = (body) => request("/api/channels", { method: "POST", body: JSON.stringify(body) });
export const createService = (body) => request("/api/services", { method: "POST", body: JSON.stringify(body) });
export const updateService = (id, body) => request(`/api/services/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteService = (id) => request(`/api/services/${id}`, { method: "DELETE" });
export const runServiceCheck = (id) => request(`/api/services/${id}/check`, { method: "POST" });
export const createIncident = (body) => request("/api/incidents", { method: "POST", body: JSON.stringify(body) });

/* ---------------- Mutations ---------------- */

export const acknowledgeIncident = (id) =>
  request(`/api/incidents/${id}/ack`, { method: "POST", body: "{}" });

export const addIncidentNote = (id, body) =>
  request(`/api/incidents/${id}/notes`, { method: "POST", body: JSON.stringify({ body }) });

export const resolveIncident = (id, summary) =>
  request(`/api/incidents/${id}/resolve`, { method: "POST", body: JSON.stringify({ summary }) });

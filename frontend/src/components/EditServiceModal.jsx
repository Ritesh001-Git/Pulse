import { useState } from "react";
import Modal from "./Modal.jsx";
import { useUpdateService } from "../api/hooks.js";
import * as api from "../api/client.js";

const num = (v, dflt) => (v === null || v === undefined ? dflt : v);

export default function EditServiceModal({ service, onClose }) {
  const [form, setForm] = useState({
    name: service.name,
    description: service.description ?? "",
    url: service.url,
    healthPath: service.healthPath,
    checkIntervalSec: num(service.checkIntervalSec, 30),
    timeoutMs: num(service.timeoutMs, 5000),
    degradedLatencyMs: num(service.degradedLatencyMs, 1000),
    failureThreshold: num(service.failureThreshold, 3),
    recoveryThreshold: num(service.recoveryThreshold, 2),
    teamOwner: service.owner ?? "",
    isActive: service.isActive,
  });
  const [error, setError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const update = useUpdateService(service.id);

  const doDelete = async () => {
    try {
      await api.deleteService(service.id);
      window.location.assign("/services");
    } catch (err) {
      setError(err.message || "Delete failed");
    }
  };

  const set = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({
        ...form,
        name: form.name.trim(),
        url: form.url.trim(),
        description: form.description.trim() || null,
        teamOwner: form.teamOwner.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err.message || "Update failed");
    }
  };

  return (
    <Modal title={`Edit ${service.name}`} onClose={onClose} width={560}>
      <form onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <div className="badge badge--down">{error}</div>}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Name</label>
            <input className="input" style={{ marginTop: 4 }} value={form.name} onChange={set("name")} />
          </div>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Team / owner</label>
            <input className="input" style={{ marginTop: 4 }} value={form.teamOwner} onChange={set("teamOwner")} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "3fr 1fr", gap: 12 }}>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Base URL</label>
            <input className="input" style={{ marginTop: 4 }} value={form.url} onChange={set("url")} />
          </div>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Health path</label>
            <input className="input" style={{ marginTop: 4 }} value={form.healthPath} onChange={set("healthPath")} />
          </div>
        </div>
        <div>
          <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Description</label>
          <input className="input" style={{ marginTop: 4 }} value={form.description} onChange={set("description")} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Interval (s)</label>
            <input className="input" type="number" style={{ marginTop: 4 }} value={form.checkIntervalSec} onChange={set("checkIntervalSec")} />
          </div>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Timeout (ms)</label>
            <input className="input" type="number" style={{ marginTop: 4 }} value={form.timeoutMs} onChange={set("timeoutMs")} />
          </div>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Degraded at (ms)</label>
            <input className="input" type="number" style={{ marginTop: 4 }} value={form.degradedLatencyMs} onChange={set("degradedLatencyMs")} />
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Failure threshold</label>
            <input className="input" type="number" style={{ marginTop: 4 }} value={form.failureThreshold} onChange={set("failureThreshold")} />
          </div>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Recovery threshold</label>
            <input className="input" type="number" style={{ marginTop: 4 }} value={form.recoveryThreshold} onChange={set("recoveryThreshold")} />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", paddingBottom: 8 }}>
            <label className="row" style={{ gap: 8, fontSize: 13 }}>
              <input type="checkbox" checked={form.isActive} onChange={set("isActive")} />
              Monitoring active
            </label>
          </div>
        </div>
        <div className="row spread" style={{ marginTop: 6 }}>
          {confirmDelete ? (
            <div className="row" style={{ gap: 8 }}>
              <span style={{ fontSize: 13, color: "#dc2626" }}>Delete {service.name} and its history?</span>
              <button type="button" className="btn" onClick={() => setConfirmDelete(false)}>Keep</button>
              <button
                type="button" onClick={doDelete}
                style={{ background: "#dc2626", color: "#fff" }}
                className="btn"
              >
                Delete for real
              </button>
            </div>
          ) : (
            <button type="button" className="btn" onClick={() => setConfirmDelete(true)}>
              🗑 Delete
            </button>
          )}
          <div className="row" style={{ gap: 10 }}>
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

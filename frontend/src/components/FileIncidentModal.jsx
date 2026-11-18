import { useState } from "react";
import Modal from "./Modal.jsx";
import { createIncident } from "../api/client.js";

export default function FileIncidentModal({ services, onClose, onCreated }) {
  const [serviceId, setServiceId] = useState(services[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState("outage");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!serviceId) return setError("Pick a service");
    if (!title.trim()) return setError("Title is required");
    setBusy(true);
    try {
      const created = await createIncident({ serviceId, title: title.trim(), severity });
      onCreated?.(created);
      onClose();
    } catch (err) {
      setError(err.status === 409 ? err.message : err.message || "Failed to file incident");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="File incident" onClose={onClose}>
      <form onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {error && <div className="badge badge--down">{error}</div>}
        <div>
          <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Service</label>
          <select className="input" style={{ marginTop: 4 }} value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
            {services.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Title</label>
          <input className="input" style={{ marginTop: 4 }} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Checkout errors spiking" autoFocus />
        </div>
        <div>
          <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Severity</label>
          <select className="input" style={{ marginTop: 4 }} value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="outage">Outage</option>
            <option value="degradation">Degradation</option>
          </select>
        </div>
        <div className="row" style={{ gap: 10, justifyContent: "flex-end", marginTop: 6 }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Filing…" : "File incident"}</button>
        </div>
      </form>
    </Modal>
  );
}

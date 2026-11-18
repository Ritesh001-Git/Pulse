import { useState } from "react";
import Modal from "./Modal.jsx";
import { createService } from "../api/client.js";

const EMPTY = {
  name: "",
  description: "",
  url: "",
  healthPath: "/health",
  checkIntervalSec: 30,
  timeoutMs: 5000,
  degradedLatencyMs: 1000,
  failureThreshold: 3,
  recoveryThreshold: 2,
  teamOwner: "",
};

function validate(form) {
  const errs = {};
  if (!form.name.trim()) errs.name = "Name is required";
  else if (form.name.trim().length > 120) errs.name = "Max 120 characters";

  if (!form.url.trim()) errs.url = "URL is required";
  else if (!/^https?:\/\/[^\s/$.?#].[^\s]*$/i.test(form.url.trim()) && !/^https?:\/\/[^\s]+$/i.test(form.url.trim()))
    errs.url = "Must be a valid http(s) URL";

  if (form.healthPath && !form.healthPath.startsWith("/")) errs.healthPath = "Path must start with /";

  const numeric = [
    ["checkIntervalSec", 5, 3600, "Check interval"],
    ["timeoutMs", 100, 30000, "Timeout"],
    ["degradedLatencyMs", 1, 60000, "Degraded latency"],
    ["failureThreshold", 1, 20, "Failure threshold"],
    ["recoveryThreshold", 1, 20, "Recovery threshold"],
  ];
  for (const [key, min, max, label] of numeric) {
    const v = Number(form[key]);
    if (!Number.isFinite(v) || v < min || v > max) errs[key] = `${label} must be ${min}–${max}`;
  }
  if (Number(form.degradedLatencyMs) >= Number(form.timeoutMs))
    errs.degradedLatencyMs = "Degraded latency must be below the timeout";
  return errs;
}

export default function RegisterServiceModal({ onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY);
  const [fieldErrors, setFieldErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setServerError(null);
    const errs = validate(form);
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;

    setBusy(true);
    try {
      const payload = {
        ...form,
        name: form.name.trim(),
        url: form.url.trim(),
        description: form.description.trim() || null,
        teamOwner: form.teamOwner.trim() || null,
        checkIntervalSec: Number(form.checkIntervalSec),
        timeoutMs: Number(form.timeoutMs),
        degradedLatencyMs: Number(form.degradedLatencyMs),
        failureThreshold: Number(form.failureThreshold),
        recoveryThreshold: Number(form.recoveryThreshold),
      };
      const created = await createService(payload);
      setSuccess(created);
      onCreated?.(created);
    } catch (err) {
      if (err.status === 409) setServerError(err.message);
      else if (err.status === 422) setServerError("Validation failed on the server — check the values.");
      else setServerError(err.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  if (success) {
    return (
      <Modal title="Service registered" onClose={onClose}>
        <div className="stack" style={{ gap: 14 }}>
          <div className="badge" style={{ background: "rgba(22,163,74,.12)", color: "#16a34a", width: "fit-content" }}>
            ✅ {success.name} is now monitored
          </div>
          <p className="muted" style={{ fontSize: 13 }}>
            The scheduler picked it up automatically — the first health check runs within{" "}
            {success.checkIntervalSec}s. It appears in the list as <strong>pending</strong> until then.
          </p>
          <button className="btn btn-primary" onClick={onClose} style={{ justifyContent: "center" }}>
            Done
          </button>
        </div>
      </Modal>
    );
  }

  const Field = ({ label, error, children }) => (
    <div>
      <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>{label}</label>
      <div style={{ marginTop: 4 }}>{children}</div>
      {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 3 }}>{error}</div>}
    </div>
  );

  return (
    <Modal title="Register service" onClose={onClose} width={560}>
      <form onSubmit={submit} className="stack" style={{ gap: 12 }}>
        {serverError && <div className="badge badge--down">{serverError}</div>}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Name *" error={fieldErrors.name}>
            <input className="input" value={form.name} onChange={set("name")} placeholder="checkout-api" autoFocus />
          </Field>
          <Field label="Team / owner">
            <input className="input" value={form.teamOwner} onChange={set("teamOwner")} placeholder="Payments" />
          </Field>
        </div>

        <Field label="Base URL *" error={fieldErrors.url}>
          <input className="input" value={form.url} onChange={set("url")} placeholder="http://localhost:7001" />
        </Field>

        <Field label="Health path" error={fieldErrors.healthPath}>
          <input className="input" value={form.healthPath} onChange={set("healthPath")} placeholder="/health" />
        </Field>

        <Field label="Description">
          <input className="input" value={form.description} onChange={set("description")} placeholder="What does this service do?" />
        </Field>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          <Field label="Interval (s)" error={fieldErrors.checkIntervalSec}>
            <input className="input" type="number" min="5" max="3600" value={form.checkIntervalSec} onChange={set("checkIntervalSec")} />
          </Field>
          <Field label="Timeout (ms)" error={fieldErrors.timeoutMs}>
            <input className="input" type="number" min="100" max="30000" value={form.timeoutMs} onChange={set("timeoutMs")} />
          </Field>
          <Field label="Degraded at (ms)" error={fieldErrors.degradedLatencyMs}>
            <input className="input" type="number" min="1" value={form.degradedLatencyMs} onChange={set("degradedLatencyMs")} />
          </Field>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
          <Field label="Failure threshold" error={fieldErrors.failureThreshold}>
            <input className="input" type="number" min="1" max="20" value={form.failureThreshold} onChange={set("failureThreshold")} />
          </Field>
          <Field label="Recovery threshold" error={fieldErrors.recoveryThreshold}>
            <input className="input" type="number" min="1" max="20" value={form.recoveryThreshold} onChange={set("recoveryThreshold")} />
          </Field>
        </div>

        <div className="row" style={{ gap: 10, justifyContent: "flex-end", marginTop: 6 }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Registering…" : "Register service"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

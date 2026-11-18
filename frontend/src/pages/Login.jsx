import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate("/");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  if (user) {
    navigate("/");
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--sidebar-bg)",
    }}>
      <div className="card" style={{ width: 380, padding: 32 }}>
        <div className="row" style={{ gap: 10, marginBottom: 6 }}>
          <span className="sidebar__logo">P</span>
          <span style={{ fontSize: 18, fontWeight: 700 }}>Pulse</span>
        </div>
        <p className="muted" style={{ fontSize: 13, marginBottom: 20 }}>
          Sign in to the service monitoring & incident console.
        </p>

        <form onSubmit={submit} className="stack" style={{ gap: 12 }}>
          {error && <div className="badge badge--down">{error}</div>}
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Email</label>
            <input
              className="input" type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com" style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <label className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Password</label>
            <input
              className="input" type="password" required value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••" style={{ marginTop: 4 }}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={busy} style={{ justifyContent: "center" }}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="muted" style={{ fontSize: 12, marginTop: 16, textAlign: "center" }}>
          Dev credentials: admin@pulse.dev / pulse123
        </div>
      </div>
    </div>
  );
}

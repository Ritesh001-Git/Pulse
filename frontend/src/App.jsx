import { Routes, Route, Link, useParams, Navigate } from "react-router-dom";
import DashboardLayout from "./layouts/DashboardLayout.jsx";
import Overview from "./pages/Overview.jsx";
import Services from "./pages/Services.jsx";
import ServiceDetail from "./pages/ServiceDetail.jsx";
import Incidents from "./pages/Incidents.jsx";
import IncidentDetail from "./pages/IncidentDetail.jsx";
import Notifications from "./pages/Notifications.jsx";
import PublicStatus from "./pages/PublicStatus.jsx";
import Login from "./pages/Login.jsx";
import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";

/** Redirects to /login when there is no session. */
function Protected({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** Remount detail pages per id so local state never leaks across records. */
function KeyedDetail({ Component, param = "id" }) {
  const params = useParams();
  return <Component key={params[param]} />;
}

function NotFound() {
  return (
    <div className="status-page">
      <div className="card" style={{ padding: 32, textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 10 }}>🧭</div>
        <h2 style={{ marginBottom: 6 }}>Page not found</h2>
        <p className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
          The page you're looking for doesn't exist.
        </p>
        <Link className="btn btn-primary" to="/">Back to Overview</Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<Protected><Overview /></Protected>} />
          <Route path="/services" element={<Protected><Services /></Protected>} />
          {/* Remounts per id — no stale state when navigating between details */}
          <Route path="/services/:id" element={<Protected><KeyedDetail Component={ServiceDetail} /></Protected>} />
          <Route path="/incidents" element={<Protected><Incidents /></Protected>} />
          <Route path="/incidents/:id" element={<Protected><KeyedDetail Component={IncidentDetail} /></Protected>} />
          <Route path="/notifications" element={<Protected><Notifications /></Protected>} />
          <Route path="*" element={<NotFound />} />
        </Route>
        {/* Public status page renders standalone — no sidebar, no auth, no internal data */}
        <Route path="/status" element={<PublicStatus />} />
      </Routes>
    </AuthProvider>
  );
}

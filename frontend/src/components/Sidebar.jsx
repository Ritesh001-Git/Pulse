import { NavLink, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

const Icon = {
  grid: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  server: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" />
      <circle cx="7" cy="7.5" r="0.5" fill="currentColor" /><circle cx="7" cy="16.5" r="0.5" fill="currentColor" />
    </svg>
  ),
  alert: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </svg>
  ),
  globe: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z" />
    </svg>
  ),
};

const NAV = [
  { to: "/", label: "Overview", icon: Icon.grid, end: true },
  { to: "/services", label: "Services", icon: Icon.server, end: false },
  { to: "/incidents", label: "Incidents", icon: Icon.alert, end: false },
  { to: "/notifications", label: "Notifications", icon: Icon.globe, end: true },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside className="sidebar">
      <Link to="/" className="sidebar__brand">
        <span className="sidebar__logo">P</span>
        <span className="sidebar__name">Pulse</span>
      </Link>

      <div className="sidebar__section">Monitoring</div>
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => "sidebar__link" + (isActive ? " sidebar__link--active" : "")}
        >
          {item.icon}
          {item.label}
        </NavLink>
      ))}

      <div className="sidebar__section">Public</div>
      <NavLink
        to="/status"
        className={({ isActive }) => "sidebar__link" + (isActive ? " sidebar__link--active" : "")}
      >
        {Icon.globe}
        Status Page
      </NavLink>

      <div className="sidebar__footer">
        <div className="sidebar__avatar">
          {(user?.name ?? "U")
            .split(" ")
            .map((p) => p[0])
            .slice(0, 2)
            .join("")}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: "#fff", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.name ?? "Signed out"}
          </div>
          <div style={{ fontSize: 12, textTransform: "capitalize" }}>{user?.role ?? ""}</div>
        </div>
        <button
          onClick={handleLogout}
          title="Sign out"
          style={{
            background: "none", border: "none", color: "var(--sidebar-text)",
            cursor: "pointer", fontSize: 15, padding: 4,
          }}
        >
          ⎋
        </button>
      </div>
    </aside>
  );
}

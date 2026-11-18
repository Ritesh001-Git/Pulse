import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar.jsx";

/** Shell for all internal (authenticated) pages. */
export default function DashboardLayout() {
  return (
    <div className="shell">
      <Sidebar />
      <main className="content">
        <div className="page">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

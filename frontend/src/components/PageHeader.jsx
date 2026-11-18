import { Link } from "react-router-dom";

export default function PageHeader({ title, subtitle, backTo, backLabel, children }) {
  return (
    <div className="page-header">
      <div>
        {backTo && (
          <div style={{ marginBottom: 8 }}>
            <Link to={backTo} className="muted" style={{ fontSize: 13 }}>
              ← {backLabel}
            </Link>
          </div>
        )}
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </div>
  );
}

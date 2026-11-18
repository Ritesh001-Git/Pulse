import { useEffect } from "react";

/** Accessible modal dialog: overlay click / Escape closes, focus trapped by DOM order. */
export default function Modal({ title, onClose, children, width = 520 }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(10,12,20,.55)", backdropFilter: "blur(2px)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
      }}
    >
      <div
        className="card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        style={{ width, maxWidth: "100%", maxHeight: "90vh", overflowY: "auto", padding: 24 }}
      >
        <div className="spread" style={{ marginBottom: 14 }}>
          <h2 style={{ fontSize: 17, fontWeight: 700 }}>{title}</h2>
          <button
            onClick={onClose} aria-label="Close" title="Close (Esc)"
            style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "var(--muted)" }}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

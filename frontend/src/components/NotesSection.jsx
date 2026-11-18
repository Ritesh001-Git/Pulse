import { useState } from "react";

function fmt(at) {
  return new Date(at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Notes list + composer. notes: [{ at, author, body }] */
export default function NotesSection({ notes = [], onAdd, busy, error }) {
  const [draft, setDraft] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (!draft.trim()) return;
    onAdd?.(draft.trim());
    setDraft("");
  };

  return (
    <div>
      {notes.length === 0 && <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>No notes yet.</div>}
      {notes.map((n, i) => (
        <div className="note-item" key={i}>
          <div className="note-meta">
            <strong style={{ color: "var(--text)" }}>{n.author}</strong> · {fmt(n.at)}
          </div>
          <div className="note-body">{n.body}</div>
        </div>
      ))}

      <form onSubmit={submit} style={{ marginTop: 14 }}>
        {error && <div className="badge badge--down" style={{ marginBottom: 8 }}>Failed to save note: {error}</div>}
        <textarea
          className="textarea"
          rows={3}
          placeholder="Add an update for the team and status page…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="spread" style={{ marginTop: 8 }}>
          <span className="muted" style={{ fontSize: 12 }}>Notes are appended to the incident timeline.</span>
          <button className="btn btn-primary" type="submit" disabled={!draft.trim() || busy}>
            {busy ? "Adding…" : "Add note"}
          </button>
        </div>
      </form>
    </div>
  );
}

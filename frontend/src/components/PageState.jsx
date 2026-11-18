import EmptyState from "./EmptyState.jsx";

/**
 * Shared async-state wrapper used by every page.
 * Renders loading skeleton, error state with retry, or children.
 */
export default function PageState({ isPending, isError, error, onRetry, children, skeletons = 1, minHeight = 280 }) {
  if (isPending) {
    return (
      <div className="stack" style={{ gap: 10, minHeight }} aria-busy="true">
        {Array.from({ length: skeletons }, (_, i) => (
          <div className="skeleton" key={i} style={{ height: i === 0 ? 64 : 48 }} />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="card">
        <EmptyState
          icon="⚠️"
          title="Something went wrong"
          hint={error?.message ?? "Failed to load data."}
        />
        {onRetry && (
          <div style={{ textAlign: "center", paddingBottom: 24 }}>
            <button className="btn" onClick={onRetry}>Retry</button>
          </div>
        )}
      </div>
    );
  }

  return children;
}

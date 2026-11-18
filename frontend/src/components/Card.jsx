export default function Card({ title, actions, children, style }) {
  return (
    <section className="card" style={style}>
      {(title || actions) && (
        <header className="card__header">
          <span className="card__title">{title}</span>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

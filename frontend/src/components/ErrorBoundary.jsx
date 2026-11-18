import { Component } from "react";

/** Catches render-time crashes so one bad page can't white-screen the app. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="status-page">
          <div className="card" style={{ padding: 32, textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 10 }}>💥</div>
            <h2 style={{ marginBottom: 6 }}>Something broke</h2>
            <p className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
              {this.state.error.message || "An unexpected error occurred."}
            </p>
            <button className="btn btn-primary" onClick={() => window.location.assign("/")}>
              Back to Overview
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

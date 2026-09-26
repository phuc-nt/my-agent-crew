import { Component, type ErrorInfo, type ReactNode } from "react";
import { vi } from "../i18n/vi";
import { Icon } from "./ui/icon";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps one broken panel from blanking the whole page; offers a reload with the message visible. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("ui crashed", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="crash" role="alert">
        <span className="crash-icon">
          <Icon name="alert" />
        </span>
        <div className="crash-text">
          <p className="crash-title">{vi.crashed}</p>
          <code className="crash-detail">{this.state.error.message}</code>
        </div>
        <button type="button" className="primary" onClick={() => window.location.reload()}>
          <Icon name="refresh" />
          {vi.reload}
        </button>
      </div>
    );
  }
}

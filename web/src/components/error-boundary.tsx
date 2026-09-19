import { Component, type ErrorInfo, type ReactNode } from "react";
import { vi } from "../i18n/vi";

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
      <div className="notice error crash" role="alert">
        <p>
          {vi.crashed} <code>{this.state.error.message}</code>
        </p>
        <button type="button" onClick={() => window.location.reload()}>
          {vi.reload}
        </button>
      </div>
    );
  }
}

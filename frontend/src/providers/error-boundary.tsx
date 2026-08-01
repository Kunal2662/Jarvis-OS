import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time errors that escape everything else. Per
 * ARCHITECTURE.md section 9: shows a user-visible message, never a raw
 * stack trace; logs the full error for Developer Mode / the console.
 * React error boundaries must be class components -- there is no hooks
 * equivalent.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console -- the one sanctioned console
    // sink until the real logging transport (WebSocket relay to the
    // Python backend's loguru pipeline) exists.
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  private reset = (): void => this.setState({ error: null });

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="flex h-full min-h-svh flex-col items-center justify-center gap-4 bg-background p-8 text-center text-foreground"
      >
        <p className="text-card-title font-bold">Something went wrong.</p>
        <p className="max-w-md text-secondary text-muted-foreground">
          {error.message || "An unexpected error occurred."}
        </p>
        <button
          type="button"
          onClick={this.reset}
          className="rounded-md bg-primary px-4 py-2 text-primary-foreground text-secondary font-medium"
        >
          Try again
        </button>
      </div>
    );
  }
}

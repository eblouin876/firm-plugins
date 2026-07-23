import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface ApiErrorBoundaryProps {
  children: ReactNode;
  /**
   * Rendered when a descendant throws during render/commit. Receives the
   * caught error — an `ApiError` when the throw came from `unwrap`, otherwise
   * whatever was thrown — and a `reset` fn that clears the boundary so the
   * subtree can re-mount and retry.
   */
  fallback: (error: Error, reset: () => void) => ReactNode;
  /** Optional side-effect hook (logging/telemetry) invoked on catch. */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ApiErrorBoundaryState {
  error: Error | null;
}

/**
 * Framework-neutral React error boundary. A class component because error
 * boundaries have no hook equivalent — `getDerivedStateFromError` /
 * `componentDidCatch` are the only APIs that catch a render-phase throw. It
 * makes no assumptions about a router or a design system: the app supplies the
 * `fallback` render. Pairs with `unwrap` — an `ApiError` thrown from a query
 * that isn't caught closer lands here.
 */
export class ApiErrorBoundary extends Component<ApiErrorBoundaryProps, ApiErrorBoundaryState> {
  state: ApiErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ApiErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError?.(error, info);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error !== null) return this.props.fallback(error, this.reset);
    return this.props.children;
  }
}

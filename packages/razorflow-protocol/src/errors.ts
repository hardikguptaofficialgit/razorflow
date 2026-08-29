/** Typed SDK / transport errors. */

export type RazorFlowErrorCode =
  | "TRANSPORT_DISCONNECTED"
  | "TRANSPORT_CONNECT_FAILED"
  | "RUN_FAILED"
  | "RUN_CANCELLED"
  | "RUN_TIMEOUT"
  | "INVALID_MESSAGE"
  | "ENVIRONMENT_ERROR";

export class RazorFlowError extends Error {
  readonly code: RazorFlowErrorCode;
  readonly recoverable: boolean;
  readonly runId?: string;

  constructor(
    code: RazorFlowErrorCode,
    message: string,
    options?: { recoverable?: boolean; runId?: string; cause?: unknown },
  ) {
    super(message);
    this.name = "RazorFlowError";
    this.code = code;
    this.recoverable = options?.recoverable ?? false;
    this.runId = options?.runId;
    if (options?.cause !== undefined) {
      (this as Error & { cause?: unknown }).cause = options.cause;
    }
  }
}

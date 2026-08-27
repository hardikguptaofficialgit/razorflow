declare module "@moonshine-ai/moonshine-js" {
  export interface TranscriberCallbacks {
    onPermissionsRequested: () => unknown;
    onError: (error: string) => unknown;
    onModelLoadStarted: () => unknown;
    onModelLoaded: () => unknown;
    onTranscribeStarted: () => unknown;
    onTranscribeStopped: () => unknown;
    onTranscriptionUpdated: (text: string) => unknown;
    onTranscriptionCommitted: (text: string, buffer?: AudioBuffer) => unknown;
    onFrame: (probs: unknown, frame: unknown, ema: unknown) => unknown;
    onSpeechStart: () => unknown;
    onSpeechEnd: () => unknown;
  }

  export const MoonshineError: {
    PermissionDenied: string;
    PlatformUnsupported: string;
  };

  export class MicrophoneTranscriber {
    constructor(
      modelURL: string,
      callbacks?: Partial<TranscriberCallbacks>,
      useVAD?: boolean,
      precision?: string,
    );
    start(): Promise<void>;
    stop(): void;
  }
}

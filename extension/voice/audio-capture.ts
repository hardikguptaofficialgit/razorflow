/**
 * Thin microphone access helper. Moonshine's MicrophoneTranscriber owns the
 * live stream; this module is reserved for future custom capture paths.
 */

export type MicPermissionState = "granted" | "denied" | "prompt" | "unknown";

export async function queryMicPermission(): Promise<MicPermissionState> {
  if (!navigator.permissions?.query) {
    return "unknown";
  }

  try {
    const status = await navigator.permissions.query({
      name: "microphone" as PermissionName,
    });
    return status.state as MicPermissionState;
  } catch {
    return "unknown";
  }
}

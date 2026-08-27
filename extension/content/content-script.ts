import { ActionPlayer } from "./action-playback";
import { registerMessageListener } from "./message-handler";
import { OverlayController } from "./overlay-state";
import { initOverlayVoice } from "./overlay-voice";

declare global {
  // Shared across re-injections in the extension isolated world.
  // eslint-disable-next-line no-var
  var __razorflowContentBoot:
    | { controller: OverlayController; player: ActionPlayer }
    | undefined;
}

function bootContentScript(): void {
  if (globalThis.__razorflowContentBoot) {
    return;
  }

  const controller = new OverlayController();
  const actionPlayer = new ActionPlayer(controller);
  registerMessageListener(controller, actionPlayer);
  initOverlayVoice(controller.getElements());
  globalThis.__razorflowContentBoot = { controller, player: actionPlayer };
}

bootContentScript();

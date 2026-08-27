export const LOGO_ASSET_PATH = "assets/logo.png";
export const DOCK_TEXTURE_ASSET_PATH = "assets/dock-texture.png";

export function getBrandLogoUrl(): string {
  return chrome.runtime.getURL(LOGO_ASSET_PATH);
}

export function getDockTextureUrl(): string {
  return chrome.runtime.getURL(DOCK_TEXTURE_ASSET_PATH);
}

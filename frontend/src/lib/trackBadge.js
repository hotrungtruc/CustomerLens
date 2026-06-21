// Shared utility — dùng chung giữa CameraStream và Dashboard right panel
// Đảm bảo badge chữ cái + màu luôn khớp nhau

export const TRACK_BADGE_THEMES = [
  { base: "bg-sky-500", ring: "ring-sky-300/80" },
  { base: "bg-fuchsia-500", ring: "ring-fuchsia-300/80" },
  { base: "bg-amber-500", ring: "ring-amber-300/80" },
  { base: "bg-emerald-500", ring: "ring-emerald-300/80" },
  { base: "bg-indigo-500", ring: "ring-indigo-300/80" },
  { base: "bg-rose-500", ring: "ring-rose-300/80" },
];

export function getTrackBadge(trackId) {
  const safeTrack = Number(trackId || 0);
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const symbol =
    safeTrack > 0 ? alphabet[(safeTrack - 1) % alphabet.length] : "?";
  return {
    symbol,
    theme: TRACK_BADGE_THEMES[safeTrack % TRACK_BADGE_THEMES.length],
  };
}

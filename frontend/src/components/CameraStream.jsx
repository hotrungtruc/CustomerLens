import { API_BASE_URL } from "../services/api";

export default function CameraStream() {
  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-black/5 bg-ink/95">
      <img
        src={`${API_BASE_URL}/video_feed`}
        alt="Camera feed"
        className="h-[420px] w-full object-cover"
      />
    </div>
  );
}

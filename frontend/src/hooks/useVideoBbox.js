import { useState, useEffect } from "react";

/**
 * Maps bounding boxes from original backend frame coordinates to an object-cover container.
 * It uses the actual <video> intrinsic dimensions for CSS object-cover math.
 */
export function useVideoBbox(containerRef, frameWidth, frameHeight) {
  const [containerSize, setContainerSize] = useState({ cw: 0, ch: 0 });
  const [videoSize, setVideoSize] = useState({ vw: 0, vh: 0 });

  // Watch container dimensions
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      if (entries[0]) {
        setContainerSize({
          cw: entries[0].contentRect.width,
          ch: entries[0].contentRect.height,
        });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [containerRef]);

  // Watch intrinsic video dimensions
  useEffect(() => {
    const video = containerRef.current;
    if (!video) return;

    const updateVideoSize = () => {
      if (video.videoWidth && video.videoHeight) {
        setVideoSize({ vw: video.videoWidth, vh: video.videoHeight });
      }
    };

    video.addEventListener("loadedmetadata", updateVideoSize);
    video.addEventListener("resize", updateVideoSize);
    
    // Poll to catch any silent WebRTC track resolution changes
    const interval = setInterval(updateVideoSize, 1000);
    updateVideoSize();

    return () => {
      video.removeEventListener("loadedmetadata", updateVideoSize);
      video.removeEventListener("resize", updateVideoSize);
      clearInterval(interval);
    };
  }, [containerRef]);

  // Map absolute backend coordinates (px) to percentage coordinates (%) of the container
  function mapBbox(x, y, w, h) {
    const { cw, ch } = containerSize;
    const { vw, vh } = videoSize;

    const fw = frameWidth || 640;
    const fh = frameHeight || 360;
    
    // Position of bbox in percentages relative to the source image
    const pctX = x / fw;
    const pctY = y / fh;
    const pctW = w / fw;
    const pctH = h / fh;

    if (!cw || !ch || !vw || !vh) {
      // Fallback: simple percentage clamped to [0, 100]
      const left = Math.max(0, Math.min(100, pctX * 100));
      const top = Math.max(0, Math.min(100, pctY * 100));
      const width = Math.max(0, Math.min(100 - left, pctW * 100));
      const height = Math.max(0, Math.min(100 - top, pctH * 100));
      return { left, top, width, height };
    }

    // Calculate object-cover math using the ACTUAL video intrinsic dimensions
    const scale = Math.max(cw / vw, ch / vh);
    const renderedW = vw * scale;
    const renderedH = vh * scale;
    const offsetX = (cw - renderedW) / 2;
    const offsetY = (ch - renderedH) / 2;

    const rawLeft = ((offsetX + pctX * renderedW) / cw) * 100;
    const rawTop = ((offsetY + pctY * renderedH) / ch) * 100;
    const rawWidth = ((pctW * renderedW) / cw) * 100;
    const rawHeight = ((pctH * renderedH) / ch) * 100;

    // Clamp strictly within visible container boundaries [0, 100]%
    const left = Math.max(0, Math.min(100, rawLeft));
    const top = Math.max(0, Math.min(100, rawTop));
    const right = Math.max(0, Math.min(100, rawLeft + rawWidth));
    const bottom = Math.max(0, Math.min(100, rawTop + rawHeight));
    const width = Math.max(0, right - left);
    const height = Math.max(0, bottom - top);

    return {
      left,
      top,
      width,
      height,
    };
  }

  return mapBbox;
}

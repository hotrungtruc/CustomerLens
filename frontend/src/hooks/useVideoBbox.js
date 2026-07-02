import { useState, useEffect } from "react";

/**
 * Maps bounding boxes from original video coordinates to an object-cover container.
 */
export function useVideoBbox(containerRef, videoWidth, videoHeight) {
  const [containerSize, setContainerSize] = useState({ cw: 0, ch: 0 });

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

  // Map absolute video coordinates (px) to percentage coordinates (%) of the container
  function mapBbox(x, y, w, h) {
    const { cw, ch } = containerSize;
    if (!cw || !ch || !videoWidth || !videoHeight) {
      // Fallback: simple percentage if size not available
      const fw = videoWidth || 640;
      const fh = videoHeight || 360;
      return {
        left: (x / fw) * 100,
        top: (y / fh) * 100,
        width: (w / fw) * 100,
        height: (h / fh) * 100,
      };
    }

    // object-cover math
    const scale = Math.max(cw / videoWidth, ch / videoHeight);
    const renderedW = videoWidth * scale;
    const renderedH = videoHeight * scale;
    const offsetX = (cw - renderedW) / 2;
    const offsetY = (ch - renderedH) / 2;

    return {
      left: ((offsetX + x * scale) / cw) * 100,
      top: ((offsetY + y * scale) / ch) * 100,
      width: ((w * scale) / cw) * 100,
      height: ((h * scale) / ch) * 100,
    };
  }

  return mapBbox;
}

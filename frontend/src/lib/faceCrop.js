/**
 * Crop face from video frame and resize to 112×112 JPEG blob
 * @param {HTMLVideoElement} videoEl - Video element
 * @param {Object} bbox - { x, y, width, height } in pixels
 * @param {number} outputSize - Output size, default 112
 * @returns {Promise<Blob>} JPEG blob (~3–5KB)
 */
export function cropFaceToBlob(videoEl, bbox, outputSize = 112) {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement("canvas");
    canvas.width = outputSize;
    canvas.height = outputSize;
    const ctx = canvas.getContext("2d");

    if (!ctx) {
      reject(new Error("Failed to get canvas context"));
      return;
    }

    // Add 15% margin around bounding box to capture full face
    const margin = 0.15;
    const mx = bbox.width * margin;
    const my = bbox.height * margin;

    const sx = Math.max(0, bbox.x - mx);
    const sy = Math.max(0, bbox.y - my);
    const sw = Math.min(videoEl.videoWidth - sx, bbox.width + mx * 2);
    const sh = Math.min(videoEl.videoHeight - sy, bbox.height + my * 2);

    // Draw cropped region scaled to 112×112
    ctx.drawImage(videoEl, sx, sy, sw, sh, 0, 0, outputSize, outputSize);

    // Export as JPEG with quality 0.85
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("canvas.toBlob failed"));
        }
      },
      "image/jpeg",
      0.85,
    );
  });
}

/**
 * Alternative: crop face to base64 string (faster for some use cases)
 */
export function cropFaceToBase64(videoEl, bbox, outputSize = 112) {
  const canvas = document.createElement("canvas");
  canvas.width = outputSize;
  canvas.height = outputSize;
  const ctx = canvas.getContext("2d");

  if (!ctx) {
    throw new Error("Failed to get canvas context");
  }

  const margin = 0.15;
  const mx = bbox.width * margin;
  const my = bbox.height * margin;
  const sx = Math.max(0, bbox.x - mx);
  const sy = Math.max(0, bbox.y - my);
  const sw = Math.min(videoEl.videoWidth - sx, bbox.width + mx * 2);
  const sh = Math.min(videoEl.videoHeight - sy, bbox.height + my * 2);

  ctx.drawImage(videoEl, sx, sy, sw, sh, 0, 0, outputSize, outputSize);

  // Return base64 without data URL prefix
  return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
}

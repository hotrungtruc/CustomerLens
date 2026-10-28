"use client";

import * as ort from "onnxruntime-web";

// Configure WASM asset location: prefer local root "/", fallback to CDN
if (typeof window !== "undefined") {
  try {
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.wasmPaths = "/";
  } catch (_) {}
}

let scrfdSession = null;
let isInitializing = false;
let initPromise = null;

const STRIDES = [8, 16, 32];
const NUM_ANCHORS = 2;
const NMS_THRESHOLD = 0.4;
const DEFAULT_DET_THRESHOLD = 0.45;

/**
 * Initialize SCRFD ONNX Session
 */
export async function initSCRFD(modelPath = "/models/scrfd_500m_bnkps.onnx") {
  if (scrfdSession) return scrfdSession;
  if (isInitializing) return initPromise;

  isInitializing = true;
  initPromise = (async () => {
    try {
      // Pre-fetch model as ArrayBuffer to bypass any internal bundler URL resolution issues
      let modelSource = modelPath;
      try {
        const resp = await fetch(modelPath);
        if (resp.ok) {
          modelSource = await resp.arrayBuffer();
        }
      } catch (fErr) {
        console.warn("Direct fetch of model failed, using modelPath:", fErr);
      }

      const optimalThreads = typeof navigator !== "undefined" && navigator.hardwareConcurrency
        ? Math.min(4, Math.max(1, Math.floor(navigator.hardwareConcurrency / 2)))
        : 2;
      ort.env.wasm.numThreads = optimalThreads;
      ort.env.wasm.proxy = false;

      // Priority 1: WebGPU execution provider (Fastest on modern browsers)
      try {
        scrfdSession = await ort.InferenceSession.create(modelSource, {
          executionProviders: ["webgpu"],
          graphOptimizationLevel: "all",
        });
        console.log("✓ Edge SCRFD (ONNX Runtime Web) initialized with WebGPU provider");
        return scrfdSession;
      } catch (webgpuErr) {
        console.warn("WebGPU provider failed/unsupported, trying local WASM provider:", webgpuErr);
      }

      // Priority 2: Local WASM provider
      try {
        ort.env.wasm.wasmPaths = "/";
        scrfdSession = await ort.InferenceSession.create(modelSource, {
          executionProviders: ["wasm"],
          graphOptimizationLevel: "all",
        });
        console.log(`✓ Edge SCRFD (ONNX Runtime Web) initialized with local WASM provider (${optimalThreads} threads)`);
        return scrfdSession;
      } catch (localWasmErr) {
        console.warn("Local WASM failed, trying CDN WASM provider:", localWasmErr);
      }

      // Priority 3: Remote CDN WASM provider
      ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.0/dist/";
      scrfdSession = await ort.InferenceSession.create(modelSource, {
        executionProviders: ["wasm"],
        graphOptimizationLevel: "all",
      });
      console.log("✓ Edge SCRFD (ONNX Runtime Web) initialized with CDN WASM provider");
      return scrfdSession;
    } catch (err) {
      console.error("Failed to initialize SCRFD ONNX:", err);
      scrfdSession = null;
      throw err;
    } finally {
      isInitializing = false;
    }
  })();

  return initPromise;
}

/**
 * Perform Non-Maximum Suppression (NMS)
 */
function nms(candidates, threshold = NMS_THRESHOLD) {
  candidates.sort((a, b) => b.score - a.score);
  const selected = [];
  const active = new Array(candidates.length).fill(true);

  for (let i = 0; i < candidates.length; i++) {
    if (!active[i]) continue;
    const a = candidates[i];
    selected.push(a);

    const aArea = a.width * a.height;
    for (let j = i + 1; j < candidates.length; j++) {
      if (!active[j]) continue;
      const b = candidates[j];

      const xA = Math.max(a.x1, b.x1);
      const yA = Math.max(a.y1, b.y1);
      const xB = Math.min(a.x2, b.x2);
      const yB = Math.min(a.y2, b.y2);

      const interW = Math.max(0, xB - xA);
      const interH = Math.max(0, yB - yA);
      const interArea = interW * interH;

      if (interArea > 0) {
        const bArea = b.width * b.height;
        const iou = interArea / (aArea + bArea - interArea);
        if (iou > threshold) {
          active[j] = false;
        }
      }
    }
  }

  return selected;
}

// Reusable canvas, context, and Float32 buffer for inference to eliminate GC stalls
let canvas = null;
let ctx = null;
let cachedFloat32 = null;
let cachedTotalPixels = 0;

/**
 * Detect faces in video frame using SCRFD ONNX
 */
export async function detectFacesSCRFD(video, detThreshold = DEFAULT_DET_THRESHOLD) {
  if (!scrfdSession || !video || video.readyState < 2) {
    return [];
  }

  const videoW = video.videoWidth;
  const videoH = video.videoHeight;
  if (!videoW || !videoH) return [];

  // Determine target inference dimensions: 640 width, height rounded to multiple of 32
  const targetW = 640;
  const rawH = (targetW * videoH) / videoW;
  const targetH = Math.max(320, Math.min(640, Math.round(rawH / 32) * 32));

  if (!canvas) {
    canvas = document.createElement("canvas");
    ctx = canvas.getContext("2d", { willReadFrequently: true });
  }

  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }

  // Draw scaled video frame
  ctx.drawImage(video, 0, 0, targetW, targetH);
  const imgData = ctx.getImageData(0, 0, targetW, targetH);
  const data = imgData.data;

  // Preprocessing: Convert RGBA to planar RGB, normalized: (pixel - 127.5) / 128.0
  const totalPixels = targetW * targetH;
  if (!cachedFloat32 || cachedTotalPixels !== totalPixels) {
    cachedFloat32 = new Float32Array(3 * totalPixels);
    cachedTotalPixels = totalPixels;
  }
  const float32 = cachedFloat32;
  const planeG = totalPixels;
  const planeB = 2 * totalPixels;

  for (let i = 0; i < totalPixels; i++) {
    const idx = i * 4;
    float32[i] = (data[idx] - 127.5) * 0.0078125;           // R
    float32[planeG + i] = (data[idx + 1] - 127.5) * 0.0078125; // G
    float32[planeB + i] = (data[idx + 2] - 127.5) * 0.0078125; // B
  }

  const inputTensor = new ort.Tensor("float32", float32, [1, 3, targetH, targetW]);
  const inputName = scrfdSession.inputNames[0] || "input.1";

  // Run inference
  const results = await scrfdSession.run({ [inputName]: inputTensor });

  // Post-process FPN Strides (8, 16, 32)
  const scaleX = videoW / targetW;
  const scaleY = videoH / targetH;
  const candidates = [];

  for (const stride of STRIDES) {
    const scoreTensor = results[`score_${stride}`];
    const bboxTensor = results[`bbox_${stride}`];
    const kpsTensor = results[`kps_${stride}`];

    if (!scoreTensor || !bboxTensor) continue;

    const scores = scoreTensor.data;
    const bboxes = bboxTensor.data;
    const kpss = kpsTensor ? kpsTensor.data : null;

    const gridH = targetH / stride;
    const gridW = targetW / stride;

    for (let y = 0; y < gridH; y++) {
      const cy = y * stride;
      for (let x = 0; x < gridW; x++) {
        const cx = x * stride;
        for (let a = 0; a < NUM_ANCHORS; a++) {
          const anchorIdx = (y * gridW + x) * NUM_ANCHORS + a;
          const score = scores[anchorIdx];
          if (score >= detThreshold) {
            const bIdx = anchorIdx * 4;
            const b0 = bboxes[bIdx] * stride;
            const b1 = bboxes[bIdx + 1] * stride;
            const b2 = bboxes[bIdx + 2] * stride;
            const b3 = bboxes[bIdx + 3] * stride;

            const x1 = Math.max(0, (cx - b0) * scaleX);
            const y1 = Math.max(0, (cy - b1) * scaleY);
            const x2 = Math.min(videoW, (cx + b2) * scaleX);
            const y2 = Math.min(videoH, (cy + b3) * scaleY);
            const width = Math.max(1, x2 - x1);
            const height = Math.max(1, y2 - y1);

            // Filter out artifacts: minimum 18px, maximum 55% of frame, and realistic face aspect ratio
            const aspect = width / height;
            if (
              width >= 18 &&
              height >= 18 &&
              width <= videoW * 0.55 &&
              height <= videoH * 0.55 &&
              aspect >= 0.5 &&
              aspect <= 2.0
            ) {
              let keypoints = null;
              if (kpss) {
                const kIdx = anchorIdx * 10;
                keypoints = [];
                for (let k = 0; k < 5; k++) {
                  const kpx = (cx + kpss[kIdx + k * 2] * stride) * scaleX;
                  const kpy = (cy + kpss[kIdx + k * 2 + 1] * stride) * scaleY;
                  keypoints.push({
                    x: kpx / videoW,
                    y: kpy / videoH,
                    px: kpx,
                    py: kpy,
                  });
                }

                // Geometric validation:
                // 1. Inter-eye distance relative to face width
                const eyeDx = keypoints[1].px - keypoints[0].px;
                const eyeDy = keypoints[1].py - keypoints[0].py;
                const eyeDist = Math.hypot(eyeDx, eyeDy);
                const eyeRatio = eyeDist / width;

                // 2. Mouth should be below eyes for upright or reasonably tilted faces
                const avgEyeY = (keypoints[0].py + keypoints[1].py) / 2;
                const avgMouthY = (keypoints[3].py + keypoints[4].py) / 2;
                const isVerticalOk = avgMouthY >= avgEyeY - height * 0.05;

                // Reject non-facial patterns (reflections, window frames, signs)
                if (eyeRatio < 0.15 || eyeRatio > 0.85 || !isVerticalOk) {
                  continue;
                }
              }

              candidates.push({
                score,
                x1,
                y1,
                x2,
                y2,
                width,
                height,
                keypoints,
              });
            }
          }
        }
      }
    }
  }

  // Pre-sort candidates and limit to top 60 before NMS to maintain 30+ FPS
  if (candidates.length > 60) {
    candidates.sort((a, b) => b.score - a.score);
    candidates.length = 60;
  }

  // Apply NMS
  const finalFaces = nms(candidates, NMS_THRESHOLD);
  return finalFaces;
}

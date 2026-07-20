import cv2
import numpy as np
import onnxruntime as ort

def distance2bbox(points, distance, max_shape=None):
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    if max_shape is not None:
        x1 = np.clip(x1, 0, max_shape[1])
        y1 = np.clip(y1, 0, max_shape[0])
        x2 = np.clip(x2, 0, max_shape[1])
        y2 = np.clip(y2, 0, max_shape[0])
    return np.column_stack([x1, y1, x2, y2])

def distance2kps(points, distance, max_shape=None):
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, 0] + distance[:, i]
        py = points[:, 1] + distance[:, i + 1]
        if max_shape is not None:
            px = np.clip(px, 0, max_shape[1])
            py = np.clip(py, 0, max_shape[0])
        preds.append(px)
        preds.append(py)
    return np.column_stack(preds)

class SCRFD:
    def __init__(self, model_file, session_options=None, providers=None):
        self.session = ort.InferenceSession(model_file, sess_options=session_options, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        
        outputs = self.session.get_outputs()
        self.output_names = [o.name for o in outputs]
        self.use_kps = False
        self._num_anchors = 2
        self.fmc = 3
        self.feat_stride_fpn = [8, 16, 32]
        
        if len(outputs) == 6:
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
        elif len(outputs) == 9:
            self.fmc = 3
            self.feat_stride_fpn = [8, 16, 32]
            self.use_kps = True
            
        self.center_cache = {}
        self.nms_thresh = 0.4
        self.det_thresh = 0.5

    def forward(self, img, threshold):
        scores_list = []
        bboxes_list = []
        kpss_list = []
        input_size = tuple(img.shape[0:2][::-1])
        blob = cv2.dnn.blobFromImage(img, 1.0/128, input_size, (127.5, 127.5, 127.5), swapRB=True)
        net_outs = self.session.run(self.output_names, {self.input_name: blob})
        
        input_height = blob.shape[2]
        input_width = blob.shape[3]
        fmc = self.fmc
        for idx, stride in enumerate(self.feat_stride_fpn):
            scores = net_outs[idx]
            bbox_preds = net_outs[idx + fmc]
            bbox_preds = bbox_preds * stride
            if self.use_kps:
                kps_preds = net_outs[idx + fmc * 2] * stride
            height = input_height // stride
            width = input_width // stride
            K = height * width
            key = (height, width, stride)
            if key in self.center_cache:
                anchor_centers = self.center_cache[key]
            else:
                grid_x = np.arange(width, dtype=np.float32)
                grid_y = np.arange(height, dtype=np.float32)
                xv, yv = np.meshgrid(grid_x, grid_y)
                anchor_centers = np.stack([xv, yv], axis=-1).reshape(-1, 2)
                anchor_centers = (anchor_centers * stride).astype(np.float32)
                anchor_centers = np.broadcast_to(np.expand_dims(anchor_centers, axis=1), (K, self._num_anchors, 2))
                anchor_centers = anchor_centers.reshape(-1, 2)
                self.center_cache[key] = anchor_centers

            pos_inds = np.where(scores >= threshold)[0]
            bboxes = distance2bbox(anchor_centers, bbox_preds)
            pos_scores = scores[pos_inds]
            pos_bboxes = bboxes[pos_inds]
            scores_list.append(pos_scores)
            bboxes_list.append(pos_bboxes)
            if self.use_kps:
                kpss = distance2kps(anchor_centers, kps_preds)
                kpss = kpss.reshape((kpss.shape[0], -1, 2))
                pos_kpss = kpss[pos_inds]
                kpss_list.append(pos_kpss)
                
        return scores_list, bboxes_list, kpss_list

    def detect(self, img, input_size=None, max_num=0, metric='default'):
        if input_size is not None:
            im_ratio = float(img.shape[0]) / img.shape[1]
            model_ratio = float(input_size[1]) / input_size[0]
            if im_ratio > model_ratio:
                new_height = input_size[1]
                new_width = int(new_height / im_ratio)
            else:
                new_width = input_size[0]
                new_height = int(new_width * im_ratio)
            det_scale = float(new_height) / img.shape[0]
            resized_img = cv2.resize(img, (new_width, new_height))
            det_img = np.zeros((input_size[1], input_size[0], 3), dtype=np.float32)
            det_img[:new_height, :new_width, :] = resized_img
        else:
            det_img = img.astype(np.float32)
            det_scale = 1.0

        scores_list, bboxes_list, kpss_list = self.forward(det_img, self.det_thresh)
        
        # Check if no faces are detected
        if len(scores_list) == 0 or all(s.size == 0 for s in scores_list):
            return np.empty((0, 4)), np.empty((0, 5, 2)), np.empty((0,))
            
        scores = np.vstack([s for s in scores_list if s.size > 0])
        scores_ravel = scores.ravel()
        order = scores_ravel.argsort()[::-1]
        
        bboxes = np.vstack([b for b in bboxes_list if b.size > 0]) / det_scale
        if self.use_kps:
            kpss = np.vstack([k for k in kpss_list if k.size > 0]) / det_scale
            
        pre_det = np.hstack((bboxes, scores)).astype(np.float32, copy=False)
        pre_det = pre_det[order, :]
        keep = self.nms(pre_det)
        det = pre_det[keep, :]
        if self.use_kps:
            kpss = kpss[order, :, :]
            kpss = kpss[keep, :, :]
        else:
            kpss = None
            
        if max_num > 0 and det.shape[0] > max_num:
            area = (det[:, 2] - det[:, 0]) * (det[:, 3] - det[:, 1])
            img_center = img.shape[0] // 2, img.shape[1] // 2
            offsets = np.vstack([
                (det[:, 0] + det[:, 2]) / 2 - img_center[1],
                (det[:, 1] + det[:, 3]) / 2 - img_center[0]
            ])
            offset_dist_squared = np.sum(np.power(offsets, 2.0), 0)
            if metric == 'max':
                values = area
            else:
                values = area - offset_dist_squared * 2.0
            bindex = np.argsort(values)[::-1]
            bindex = bindex[0:max_num]
            det = det[bindex, :]
            if kpss is not None:
                kpss = kpss[bindex, :]
                
        return det[:, :4], kpss, det[:, 4]

    def nms(self, dets):
        thresh = self.nms_thresh
        x1 = dets[:, 0]
        y1 = dets[:, 1]
        x2 = dets[:, 2]
        y2 = dets[:, 3]
        scores = dets[:, 4]

        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            if order.size == 1:
                break
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0.0, xx2 - xx1 + 1)
            h = np.maximum(0.0, yy2 - yy1 + 1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)

            inds = np.where(ovr <= thresh)[0]
            order = order[inds + 1]

        return keep

# Thiết kế Camera ID cố định và tách phiên WebSocket

> Trạng thái triển khai: hoàn tất trong repo ngày 2026-06-30. Luồng production hiện dùng Camera ID từ database + HttpOnly device credential, Connection ID theo handshake, Redis presence lease, worker channel theo connection, observer bridge có RBAC, pairing recovery và takeover an toàn.

> Trạng thái tài liệu: kế hoạch kỹ thuật và code minh họa, chưa áp dụng vào source code.
>
> Phạm vi: frontend Next.js, backend FastAPI, WebSocket publisher/observer, Redis, AI worker, database và màn hình quản lý camera.

## 1. Mục tiêu của tài liệu

Tài liệu này giải thích đầy đủ:

1. Vì sao hệ thống hiện tại tạo một Camera ID mới sau mỗi lần refresh hoặc mở lại trang.
2. Những dòng code hiện tại tạo ra hành vi đó.
3. Vì sao các camera cũ tiếp tục xuất hiện dưới trạng thái Idle.
4. Cách cấp một Camera ID cố định cho trình duyệt mà không cần tài khoản.
5. Cách cookie HttpOnly được sử dụng với REST API và WebSocket handshake.
6. Cách tách Camera ID cố định khỏi Connection ID tạm thời.
7. Luồng đầy đủ từ lần truy cập đầu tiên, reconnect, worker AI, observer, disconnect đến cleanup.
8. Code đề xuất theo từng file.
9. Database schema, Redis key, bảo mật, migration và kiểm thử.

## 2. Yêu cầu nghiệp vụ

Một thiết bị mở trang chủ và bật camera phải được xem là một camera logic duy nhất.

Ví dụ thiết bị A được cấp:

~~~text
camera_id = cam_7f1c9a...
display_name = Camera cửa chính
~~~

Các hành động sau không được tạo thêm Camera ID:

- Refresh trang.
- WebSocket reconnect.
- Mất mạng rồi kết nối lại.
- Đóng và mở lại trình duyệt.
- Khởi động lại máy.
- Truy cập website mà không đăng nhập tài khoản.

Kết quả mong muốn:

~~~text
Thiết bị A
├── Lần kết nối 1: connection_id = conn_a
├── Lần kết nối 2: connection_id = conn_b
└── Lần kết nối 3: connection_id = conn_c

Tất cả đều thuộc camera_id = cam_7f1c9a...
~~~

Màn quản lý chỉ hiển thị một camera:

~~~text
Camera cửa chính — LIVE
~~~

hoặc:

~~~text
Camera cửa chính — IDLE
~~~

## 3. Thuật ngữ

| Thuật ngữ | Vòng đời | Vai trò |
|---|---|---|
| camera_id | Cố định, lưu database | Danh tính camera/điểm lắp đặt |
| device_token | Dài hạn, lưu trong cookie | Chứng minh trình duyệt thuộc camera nào |
| token_hash | Dài hạn, lưu database | Bản hash dùng để tra device_token |
| connection_id | Tạm thời, tạo cho mỗi WebSocket | Cô lập tracker, Redis và kết quả AI |
| MediaDeviceInfo.deviceId | Do browser cấp | Chọn webcam vật lý, không làm Camera ID nghiệp vụ |
| CameraState hiện tại | Lưu trong RAM | Hiện đang bị dùng lẫn cho camera và connection |
| Presence lease | TTL ngắn trong Redis | Cho biết camera đang Live hay Idle |

Điểm quan trọng:

~~~text
camera_id không phải connection_id
device_token không phải camera_id
cookie là nơi browser chứa device_token
~~~

## 4. Luồng hiện tại

### 4.1 Sơ đồ tổng quát

~~~text
Math.random()
    ↓
sessionId = camera_xxxxxxx
    ↓
/ws/{sessionId}
    ↓
get_camera_state(session_id)
    ↓
CAMERA_STATES[session_id]
    ↓
Redis channel theo session_id
    ↓
"camera_id": session_id
    ↓
Worker trả kết quả theo camera_id/session_id
~~~

Hệ thống hiện tại đang dùng cùng một giá trị cho quá nhiều nhiệm vụ:

~~~text
session_id
├── Tên hiển thị camera
├── Camera ID
├── WebSocket route parameter
├── Khóa CameraState
├── Guest tracker prefix
├── Redis worker result channel
├── Redis WebRTC signaling channel
└── camera_id trong recognize_logs
~~~

### 4.2 Frontend sinh sessionId ngẫu nhiên

File: frontend/src/app/page.jsx, khoảng dòng 289–295.

Code hiện tại:

~~~jsx
// Each browser tab gets a unique session ID so concurrent users have isolated
// backend CameraState instances and never share annotations.
const sessionIdRef = useRef(null);

if (!sessionIdRef.current && typeof window !== "undefined") {
  sessionIdRef.current =
    "camera_" + Math.random().toString(36).substring(2, 9);
}

const sessionId = sessionIdRef.current || "default";
~~~

Sau đó sessionId được truyền vào CameraStream:

~~~jsx
<CameraStream
  sessionId={sessionId}
  highlightedTrackId={highlightedTrackId}
  framed={false}
  fullHeight={true}
  onCustomersChange={handleCustomersChange}
/>
~~~

useRef chỉ giữ giá trị trong vòng đời component hiện tại. Sau refresh:

~~~text
React component bị dựng lại
    ↓
sessionIdRef trở về null
    ↓
Math.random() chạy lại
    ↓
sessionId mới
~~~

Ví dụ:

~~~text
Lần 1  → camera_325bc6e
Refresh → camera_a8d92f1
Mở lại → camera_f18d672
~~~

### 4.3 CameraStream truyền sessionId vào useCamera

File: frontend/src/components/CameraStream.jsx.

~~~jsx
export default function CameraStream({
  sessionId,
  highlightedTrackId = null,
  framed = true,
  compact = false,
  fullHeight = false,
  onCustomersChange = null,
}) {
  const {
    videoRef,
    canvasRef,
    devices,
    selectedDeviceId,
    setSelectedDeviceId,
    wsStatus,
    customers,
    frameSize,
    cameraError,
  } = useCamera(sessionId);
~~~

### 4.4 Frontend dùng sessionId để tạo URL WebSocket

File: frontend/src/hooks/useCamera.js, khoảng dòng 11–25.

~~~js
function getWsUrl(sessionId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  let host = "localhost:8000";
  const baseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_HOST;

  if (baseUrl) {
    try {
      const url = baseUrl.includes("://")
        ? new URL(baseUrl)
        : new URL("http://" + baseUrl);
      host = url.host;
    } catch (_) {
      host = baseUrl.replace(/^https?:\/\//, "");
    }
  }

  return protocol + "//" + host + "/ws/" + encodeURIComponent(sessionId);
}
~~~

Mở WebSocket:

~~~js
const ws = new WebSocket(getWsUrl(sessionId));
~~~

URL thực tế:

~~~text
wss://api.checkinface.me/ws/camera_325bc6e
~~~

### 4.5 Backend nhận session_id từ URL

File: backend/app/api/routes.py, khoảng dòng 512.

~~~python
@router.websocket("/ws/{session_id}")
async def websocket_camera(websocket: WebSocket, session_id: str):
    await websocket.accept()

    state = get_camera_state(session_id)

    r = await get_redis()
    pubsub = r.pubsub()

    await pubsub.subscribe(f"worker_results_{session_id}")
    await pubsub.subscribe(f"webrtc_signaling_{session_id}")
~~~

Backend đang gọi accept ngay khi request đến:

~~~python
await websocket.accept()
~~~

Sau đó dùng session_id làm khóa camera:

~~~python
state = get_camera_state(session_id)
~~~

### 4.6 get_camera_state tạo CameraState mới

File: backend/app/api/routes.py, khoảng dòng 76–92.

~~~python
class CameraState:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.active = True
        self.latest_jpeg = None
        self.last_frame_time = None
        self.latest_customers_payload = []


CAMERA_STATES = {}
CAMERA_STATES_LOCK = threading.Lock()


def get_camera_state(camera_id: str | None = None) -> CameraState:
    cid = (camera_id or "default").strip()

    with CAMERA_STATES_LOCK:
        if cid not in CAMERA_STATES:
            CAMERA_STATES[cid] = CameraState(cid)

        return CAMERA_STATES[cid]
~~~

Mỗi session ID mới tạo một entry mới:

~~~python
CAMERA_STATES[cid] = CameraState(cid)
~~~

### 4.7 Backend gửi session_id sang worker dưới tên camera_id

File: backend/app/api/routes.py, khoảng dòng 629–640.

~~~python
if "bytes" in msg:
    data = msg["bytes"]

    if data:
        state.latest_jpeg = bytes(data)
        state.last_frame_time = time.time()

        opeid = str(uuid.uuid4())

        meta_dict = {
            "opeid": opeid,
            "camera_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
~~~

Dòng xác nhận việc nhập nhằng:

~~~python
"camera_id": session_id
~~~

### 4.8 Worker dùng camera_id làm result channel

File: backend/app/ai_worker.py, khoảng dòng 60–123.

~~~python
opeid = data.get("opeid")
camera_id = data.get("camera_id")

if not camera_id:
    logger.warning("Received frame without camera_id. Skipping.")
    continue

# Detect và embedding...

pubsub_channel = f"worker_results_{camera_id}"

payload = {
    "opeid": opeid,
    "camera_id": camera_id,
    "timestamp": data.get("timestamp"),
    "face_records": face_records,
    "frame_size": {
        "width": frame.shape[1],
        "height": frame.shape[0],
    },
}

redis_client.publish(pubsub_channel, json.dumps(payload))
~~~

### 4.9 Active sessions tích lũy camera Idle

File: backend/app/api/routes.py, khoảng dòng 663–680.

~~~python
@router.get("/api/active_sessions")
def api_active_sessions():
    now = time.time()

    with CAMERA_STATES_LOCK:
        sessions = []

        for cid, state in CAMERA_STATES.items():
            face_count = len(state.latest_customers_payload)
            is_active = (
                state.last_frame_time is not None
                and (now - state.last_frame_time) < 10
            )

            sessions.append({
                "session_id": cid,
                "face_count": face_count,
                "active": bool(is_active),
                "last_frame_time": state.last_frame_time,
            })

    return {
        "status": "success",
        "sessions": sessions,
    }
~~~

Trong finally của publisher hiện chỉ hủy reader và unsubscribe:

~~~python
finally:
    reader_task.cancel()
    await pubsub.unsubscribe()
~~~

Không có:

~~~python
CAMERA_STATES.pop(session_id, None)
~~~

Vì vậy state cũ vẫn nằm trong RAM. active_sessions tiếp tục trả nó về với active=false.

### 4.10 Observer cũng phụ thuộc session_id

File: backend/app/api/routes.py, khoảng dòng 694.

~~~python
@router.websocket("/ws/observe/{session_id}")
async def websocket_observe(websocket: WebSocket, session_id: str):
    await websocket.accept()

    with CAMERA_STATES_LOCK:
        if session_id not in CAMERA_STATES:
            await websocket.close(code=4004, reason="Session not found")
            return

        state = CAMERA_STATES[session_id]

    r = await get_redis()
    pubsub = r.pubsub()

    await pubsub.subscribe(f"camera_results_{session_id}")
    await pubsub.subscribe(f"webrtc_signaling_{session_id}")
~~~

Observer hiện coi session_id là danh tính camera. Khi publisher refresh và có session_id mới, observer phải theo ID mới.

## 5. Kết luận nguyên nhân gốc

### 5.1 Nhập nhằng danh tính

~~~text
camera_id = websocket session_id
~~~

### 5.2 Danh tính được tạo ở sai nơi

Frontend dùng Math.random để quyết định danh tính nghiệp vụ. Backend không phải nguồn dữ liệu chuẩn.

### 5.3 Camera catalog và connection state bị gộp

CAMERA_STATES vừa đóng vai trò:

- Danh sách camera.
- Trạng thái connection.
- Latest frame.
- Latest customers.

### 5.4 Không cleanup

Disconnect không loại state cũ khỏi CAMERA_STATES.

### 5.5 Không có xác thực publisher

Backend hiện tin session_id trong URL và accept WebSocket trước khi xác thực thiết bị.

## 6. Giới hạn của nền tảng web

Browser không cung cấp một hardware ID vĩnh viễn đáng tin cậy như MAC address hoặc serial máy.

MediaDeviceInfo.deviceId:

- Dùng để chọn webcam cụ thể.
- Thường chỉ ổn định theo origin và quyền camera.
- Có thể thay đổi khi người dùng xóa dữ liệu site.
- Không nên dùng làm Camera ID nghiệp vụ.

Cookie, localStorage và IndexedDB đều có thể bị người dùng xóa.

Vì vậy giải pháp web có cam kết:

~~~text
Cùng browser profile + cookie còn tồn tại
→ tự động nhận ra camera cũ
~~~

Những trường hợp không thể tự động nhận ra:

- Xóa cookie/site data.
- Dùng Incognito.
- Đổi browser profile.
- Đổi trình duyệt.
- Cài lại hệ điều hành.

Để phục hồi Camera ID cũ trong các trường hợp đó, cần pairing code, QR hoặc native agent.

Tham khảo:

- W3C Media Capture and Streams: https://www.w3.org/TR/mediacapture-streams/
- W3C Clear Site Data: https://www.w3.org/TR/clear-site-data/
- RFC 6455 WebSocket: https://www.rfc-editor.org/rfc/rfc6455
- RFC 6265 Cookie: https://www.rfc-editor.org/rfc/rfc6265

## 7. Kiến trúc mục tiêu

### 7.1 Bốn định danh tách biệt

~~~text
camera_id
    Cố định trong database.
    Dùng cho UI, log, lịch sử, phân quyền.

device_token
    Bí mật dài hạn trong HttpOnly cookie.
    Dùng để chứng minh browser thuộc camera nào.

connection_id
    Sinh mới cho mỗi WebSocket.
    Dùng cho tracker, worker result và signaling.

media_device_id
    Do getUserMedia/enumerateDevices cung cấp.
    Chỉ dùng để chọn webcam vật lý.
~~~

### 7.2 Sơ đồ luồng mới

~~~text
POST /api/device/identity
    ↓
Browser tự gửi cookie nếu có
    ↓
Backend tra token_hash
    ↓
camera_id = cam_7f1c9a...
    ↓
/ws/{camera_id}
    ↓
Handshake tự gửi cookie
    ↓
Backend xác thực Origin + cookie + camera_id
    ↓
Sinh connection_id tạm (chưa tạo ConnectionState)
    ↓
Giữ Redis presence lease bằng connection_id tạm
    ↓
websocket.accept() → HTTP 101 Switching Protocols
    ↓
Tạo và đăng ký CONNECTION_STATES[connection_id]
    ↓
Frame metadata chứa camera_id + connection_id
    ↓
Worker result channel theo connection_id
    ↓
Log và UI theo camera_id
~~~

## 8. Cookie và device token

### 8.1 Phân biệt token và cookie

Token là giá trị bí mật:

~~~text
dev_secret_xyz
~~~

Cookie là cơ chế browser lưu và gửi token:

~~~http
Cookie: device_token=dev_secret_xyz
~~~

### 8.2 Thuộc tính đề xuất

~~~http
Set-Cookie: device_token=dev_secret_xyz;
            Path=/;
            HttpOnly;
            Secure;
            SameSite=Lax;
            Max-Age=31536000
~~~

Ý nghĩa:

- HttpOnly: JavaScript không đọc được token.
- Secure: chỉ gửi qua HTTPS/WSS.
- Path=/: gửi cho API và WebSocket path.
- SameSite=Lax: phù hợp production checkinface.me và api.checkinface.me vì cùng site.
- Max-Age: lưu dài hạn.

Frontend production:

~~~text
https://checkinface.me
~~~

Backend/WebSocket:

~~~text
https://api.checkinface.me
wss://api.checkinface.me
~~~

Hai origin khác nhau nhưng cùng site checkinface.me.

Nếu frontend ở domain Vercel còn API ở checkinface.me thì đây có thể là cross-site. Có thể cần SameSite=None; Secure và vẫn có rủi ro bị chặn third-party cookie. Production nên dùng cùng site.

### 8.3 Vì sao frontend vẫn gọi API ở lần sau

React state mất sau refresh. Frontend không đọc được HttpOnly cookie. Vì vậy frontend hỏi backend:

~~~text
Cookie mà browser đang giữ thuộc camera nào?
~~~

Backend trả:

~~~json
{
  "camera_id": "cam_7f1c9a...",
  "is_new": false
}
~~~

### 8.4 Browser tự gửi cookie

Frontend gọi:

~~~js
fetch(API_BASE_URL + "/api/device/identity", {
  method: "POST",
  credentials: "include",
});
~~~

Trong lần truy cập đầu tiên, request POST /api/device/identity chưa có device_token. Backend trả Set-Cookie và browser tự lưu. Ngay sau khi API hoàn tất, frontend mới mở WebSocket; HTTP Upgrade handshake của WebSocket trong chính lần truy cập đầu tiên đã có cookie vừa được cấp.

Trong những lần truy cập website tiếp theo, cùng code fetch POST /api/device/identity được chạy nhưng browser lấy cookie cũ đang lưu và tự đính kèm:

~~~http
Cookie: device_token=dev_secret_xyz
~~~

JavaScript không tự đặt header Cookie. Browser quản lý cookie jar và gắn cookie dựa trên domain, path, Secure và SameSite.

### 8.5 Điều kiện để browser tự gửi device_token

Browser chỉ tự đính kèm device_token vào REST request hoặc WebSocket handshake khi tất cả điều kiện liên quan đều phù hợp:

1. Cookie được backend api.checkinface.me đặt cho đúng host/domain. Khuyến nghị dùng host-only cookie của api.checkinface.me, không khai báo Domain nếu không cần chia sẻ cookie cho subdomain khác.
2. Path của cookie bao phủ URL được gọi. Path=/ bao phủ cả /api/device/identity và /ws/{camera_id}.
3. Nếu cookie có Secure thì REST phải dùng https:// và WebSocket phải dùng wss://.
4. SameSite phải phù hợp deployment. checkinface.me và api.checkinface.me là khác origin nhưng cùng site; frontend Vercel và API checkinface.me có thể là cross-site.
5. Browser chưa xóa, chưa hết hạn và không chặn cookie.
6. Với fetch cross-origin từ frontend sang API, frontend phải dùng credentials: "include" và backend phải trả Access-Control-Allow-Credentials: true cùng một Access-Control-Allow-Origin cụ thể.

Khi các điều kiện này thỏa mãn, browser tự tạo header:

~~~http
Cookie: device_token=dev_secret_xyz
~~~

Frontend JavaScript không cần và không được tự đặt header Cookie.

## 9. Luồng lần truy cập đầu tiên

~~~text
1. Browser mở trang chủ.
2. Frontend chưa render CameraStream.
3. Frontend POST /api/device/identity với credentials=include.
4. Request không có device_token.
5. Backend sinh camera_id.
6. Backend sinh device_token entropy cao.
7. Backend lưu camera vào cameras.
8. Backend lưu hash(device_token) vào camera_device_credentials.
9. Backend trả Set-Cookie HttpOnly.
10. Browser tự lưu cookie.
11. Response body trả camera_id.
12. Frontend setCameraId(camera_id).
13. Frontend render CameraStream.
14. CameraStream mở WebSocket /ws/{camera_id}.
~~~

Ví dụ request:

~~~http
POST /api/device/identity HTTP/1.1
Host: api.checkinface.me
Origin: https://checkinface.me
~~~

Response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://checkinface.me
Access-Control-Allow-Credentials: true
Set-Cookie: device_token=dev_secret_xyz; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=31536000
Content-Type: application/json

{
  "camera_id": "cam_7f1c9a...",
  "is_new": true
}
~~~

## 10. Luồng truy cập lần sau

~~~text
1. Browser mở lại website.
2. React state chưa có camera_id.
3. Frontend POST /api/device/identity.
4. Browser lấy device_token cũ đang lưu và tự đính kèm nó vào header Cookie của request; browser không tạo thêm cookie mới.
5. Backend hash token.
6. Backend tra token_hash trong database.
7. Backend tìm được camera_id cũ.
8. Backend cập nhật last_used_at.
9. Backend trả camera_id cũ.
10. Frontend render CameraStream.
11. Frontend mở WebSocket cho camera_id cũ.
~~~

Request:

~~~http
POST /api/device/identity HTTP/1.1
Host: api.checkinface.me
Origin: https://checkinface.me
Cookie: device_token=dev_secret_xyz
~~~

Response:

~~~json
{
  "camera_id": "cam_7f1c9a...",
  "is_new": false
}
~~~

## 11. WebSocket handshake mới

### 11.1 Frontend tạo URL WebSocket

Sau khi POST /api/device/identity trả camera_id, frontend dùng camera_id để tạo URL. Frontend không viết cứng CAM-001:

~~~js
const wsUrl = getWsUrl(cameraId);
const ws = new WebSocket(wsUrl);
~~~

Ví dụ:

~~~text
cameraId = cam_7f1c9a...
    ↓
getWsUrl(cameraId)
    ↓
wss://api.checkinface.me/ws/cam_7f1c9a...
    ↓
new WebSocket(wsUrl)
~~~

Lệnh new WebSocket không gửi frame ngay. Trước tiên browser phân tích URL vừa tạo và tự thực hiện HTTP Upgrade handshake.

### 11.2 Request handshake

~~~http
GET /ws/cam_7f1c9a HTTP/1.1
Host: api.checkinface.me
Origin: https://checkinface.me
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: ...
Sec-WebSocket-Version: 13
Cookie: device_token=dev_secret_xyz
~~~

HttpOnly không ngăn cookie được gửi. Nó chỉ ngăn JavaScript đọc cookie.

### 11.3 Thứ tự xử lý trước accept

~~~text
HTTP Upgrade request đang chờ
    ↓
Kiểm tra Origin
    ↓
Đọc device_token
    ↓
Tra token_hash → camera_id
    ↓
Đối chiếu camera_id trong URL
    ↓
Sinh connection_id tạm; chưa tạo ConnectionState
    ↓
Giữ Redis lease cho camera bằng connection_id tạm
    ↓
Tất cả hợp lệ
    ↓
websocket.accept()
    ↓
HTTP/1.1 101 Switching Protocols
~~~

Đây là thứ tự chuẩn được sử dụng xuyên suốt tài liệu. connection_id phải được sinh trước Redis lease vì chính nó là giá trị sở hữu lease. ConnectionState chỉ được tạo và đăng ký sau khi websocket.accept() thành công. connection_id và Redis lease không phải yêu cầu bắt buộc của RFC WebSocket; đây là điều kiện nghiệp vụ giúp hệ thống chỉ có một publisher và cô lập connection.

### 11.4 Response thành công

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

### 11.5 Sau accept

Backend thực hiện phần khởi tạo có thể tốn thời gian:

- Tạo ConnectionState.
- Tạo GuestTrackManager.
- Load known embeddings.
- Subscribe worker result.
- Subscribe WebRTC signaling.
- Cài heartbeat/lease renewal.

Sau đó gửi:

~~~json
{
  "type": "ready",
  "camera_id": "cam_7f1c9a...",
  "connection_id": "conn_a82f91"
}
~~~

Frontend chỉ bắt đầu gửi frame sau khi nhận ready.

## 12. Luồng frame và AI worker mới

### 12.1 Frontend

Frontend vẫn gửi JPEG bytes như hiện tại. Định dạng frame không đổi.

### 12.2 Metadata backend

~~~python
meta_dict = {
    "opeid": opeid,
    "camera_id": camera_id,
    "connection_id": connection_id,
    "timestamp": datetime.now().isoformat(),
}
~~~

### 12.3 Queue

Tiếp tục dùng queue chung:

~~~text
camera_frames_v2
~~~

### 12.4 Worker

Worker đọc cả camera_id và connection_id, giữ camera_id trong payload nghiệp vụ và publish kết quả vào worker_results_{connection_id}. Code hoàn chỉnh nằm ở mục 16 để tránh lặp cùng một đoạn code tại hai nơi.

### 12.5 Master nhận result

Master kiểm tra:

~~~text
connection_id còn active không?
connection_id có còn thuộc camera_id không?
Redis lease của camera có còn là connection_id này không?
~~~

Nếu không, bỏ kết quả cũ.

## 13. Presence, Live/Idle và duplicate connection

### 13.1 Redis key

~~~text
camera:presence:{camera_id}
~~~

Giá trị:

~~~json
{
  "connection_id": "conn_a82f91"
}
~~~

TTL đề xuất:

~~~text
15 giây
~~~

Renew mỗi:

~~~text
5 giây hoặc mỗi frame hợp lệ
~~~

### 13.2 Acquire

~~~python
acquired = await redis.set(
    f"camera:presence:{camera_id}",
    connection_id,
    nx=True,
    ex=15,
)
~~~

Nếu acquired là false, camera đã có publisher.

### 13.3 Release an toàn

Không được delete lease vô điều kiện vì connection cũ có thể xóa lease của connection mới.

Pseudo-Lua:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end

return 0
~~~

### 13.4 Renew an toàn

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("EXPIRE", KEYS[1], ARGV[2])
end

return 0
~~~

### 13.5 Chính sách nhiều tab

Khuyến nghị:

1. Connection đầu giữ lease.
2. Connection thứ hai bị từ chối với lý do camera đang hoạt động.
3. UI có nút Tiếp quản.
4. Takeover phải thu hồi lease cũ và thông báo connection cũ dừng reconnect.

## 14. Database schema đề xuất

### 14.1 cameras

~~~sql
CREATE TABLE cameras (
    camera_id VARCHAR(64) PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NULL
);
~~~

Camera ID nên là opaque ID:

~~~text
cam_7f1c9a0e...
~~~

CAM-001 chỉ nên là ví dụ hoặc mã hiển thị. Tên camera nằm riêng trong display_name.

### 14.2 camera_device_credentials

~~~sql
CREATE TABLE camera_device_credentials (
    credential_id VARCHAR(64) PRIMARY KEY,
    camera_id VARCHAR(64) NOT NULL,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    revoked_at TIMESTAMP NULL,
    user_agent VARCHAR(512) NULL,
    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
);
~~~

Không lưu device_token gốc.

### 14.3 recognize_logs

Bổ sung:

~~~sql
ALTER TABLE recognize_logs
ADD COLUMN connection_id VARCHAR(64) NULL;
~~~

camera_id trong recognize_logs trở thành Camera ID cố định.

### 14.4 camera_connections tùy chọn

~~~sql
CREATE TABLE camera_connections (
    connection_id VARCHAR(64) PRIMARY KEY,
    camera_id VARCHAR(64) NOT NULL,
    connected_at TIMESTAMP NOT NULL,
    disconnected_at TIMESTAMP NULL,
    disconnect_reason VARCHAR(255) NULL,
    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
);
~~~

Bảng này phục vụ audit, không dùng làm presence realtime.

### 14.5 Phân quyền observer

Trường users.cameras hiện là TEXT. Hướng chuẩn hóa:

~~~sql
CREATE TABLE user_camera_permissions (
    user_id INTEGER NOT NULL,
    camera_id VARCHAR(64) NOT NULL,
    permission VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id, camera_id, permission),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
);
~~~

## 15. Code backend đề xuất

> Các đoạn dưới đây là thiết kế tham khảo. Cần tích hợp với abstraction SQLite/PostgreSQL hiện có trong backend/app/db/connection.py.

### 15.1 Helper token

~~~python
import hashlib
import secrets
import uuid


DEVICE_COOKIE_NAME = "device_token"
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def generate_camera_id() -> str:
    return "cam_" + uuid.uuid4().hex


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
~~~

SHA-256 phù hợp ở đây vì token có entropy cao do secrets tạo. Đây không phải password do người dùng chọn.

### 15.2 API resolve-or-create

~~~python
from datetime import datetime, timezone
from fastapi import Request, Response
from fastapi.responses import JSONResponse


@router.post("/api/device/identity")
def resolve_device_identity(request: Request, response: Response):
    raw_token = request.cookies.get(DEVICE_COOKIE_NAME)

    if raw_token:
        token_hash = hash_device_token(raw_token)
        credential = find_active_device_credential(token_hash)

        if credential:
            touch_device_credential(credential["credential_id"])

            return {
                "camera_id": credential["camera_id"],
                "display_name": credential["display_name"],
                "is_new": False,
            }

        # Cookie tồn tại nhưng token không hợp lệ hoặc đã bị thu hồi.
        invalid_response = JSONResponse(
            status_code=401,
            content={
                "detail": "Device credential is invalid or revoked",
            },
        )

        invalid_response.delete_cookie(
            DEVICE_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )

        return invalid_response

    camera_id = generate_camera_id()
    raw_token = generate_device_token()
    token_hash = hash_device_token(raw_token)

    create_camera_and_credential(
        camera_id=camera_id,
        display_name="Camera mới",
        token_hash=token_hash,
        user_agent=request.headers.get("user-agent"),
    )

    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=raw_token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )

    return {
        "camera_id": camera_id,
        "display_name": "Camera mới",
        "is_new": True,
    }
~~~

Policy cần quyết định:

- Anonymous auto-enroll: không có cookie thì tạo camera mới.
- Pairing-only: không có cookie thì yêu cầu pairing code.
- Hybrid: anonymous camera ở trạng thái pending cho đến khi có frame thật hoặc admin duyệt.

Khuyến nghị nếu website public:

1. Không ghi camera vĩnh viễn ngay khi chỉ mở trang.
2. Chỉ finalize enrollment sau khi người dùng cấp quyền camera và gửi frame hợp lệ.
3. Rate-limit theo IP.
4. Tự dọn pending enrollment chưa từng stream.

### 15.3 ConnectionState

~~~python
class ConnectionState:
    def __init__(
        self,
        connection_id: str,
        camera_id: str,
        websocket: WebSocket,
    ):
        self.connection_id = connection_id
        self.camera_id = camera_id
        self.websocket = websocket
        self.latest_jpeg = None
        self.last_frame_time = None
        self.latest_customers_payload = []
        self.track_manager = None


CONNECTION_STATES = {}
CONNECTION_STATES_LOCK = threading.Lock()
~~~

### 15.4 Xác thực WebSocket

~~~python
ALLOWED_WS_ORIGINS = {
    "https://checkinface.me",
    "https://www.checkinface.me",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}


def resolve_websocket_camera(websocket: WebSocket):
    origin = websocket.headers.get("origin")

    if origin not in ALLOWED_WS_ORIGINS:
        return None, "origin_not_allowed"

    raw_token = websocket.cookies.get(DEVICE_COOKIE_NAME)

    if not raw_token:
        return None, "missing_device_token"

    token_hash = hash_device_token(raw_token)
    credential = find_active_device_credential(token_hash)

    if not credential:
        return None, "invalid_device_token"

    return credential, None
~~~

### 15.5 Publisher WebSocket đề xuất

~~~python
@router.websocket("/ws/{camera_id}")
async def websocket_camera(websocket: WebSocket, camera_id: str):
    credential, error = resolve_websocket_camera(websocket)

    if error:
        # Đóng trước accept sẽ từ chối handshake.
        # Cách trả HTTP 401/403 cụ thể phụ thuộc Starlette/Uvicorn version.
        await websocket.close()
        return

    if credential["camera_id"] != camera_id:
        await websocket.close()
        return

    # Sinh ID tạm trước accept vì Redis lease cần biết connection
    # nào đang yêu cầu quyền publisher. Chưa tạo ConnectionState ở đây.
    connection_id = "conn_" + uuid.uuid4().hex
    r = await get_redis()
    lease_key = f"camera:presence:{camera_id}"

    acquired = await r.set(
        lease_key,
        connection_id,
        nx=True,
        ex=15,
    )

    if not acquired:
        await websocket.close()
        return

    # Chỉ nâng cấp HTTP thành WebSocket sau khi xác thực và
    # acquire lease thành công.
    await websocket.accept()

    # Sau HTTP 101 mới tạo/register state realtime.
    state = ConnectionState(
        connection_id=connection_id,
        camera_id=camera_id,
        websocket=websocket,
    )

    with CONNECTION_STATES_LOCK:
        CONNECTION_STATES[connection_id] = state

    pubsub = r.pubsub()
    await pubsub.subscribe(f"worker_results_{connection_id}")
    await pubsub.subscribe(f"webrtc_signaling_{connection_id}")

    try:
        state.track_manager = GuestTrackManager(
            buffer_size=TRACK_BUFFER_SIZE,
            guest_creation_buffer_size=GUEST_CREATION_BUFFER_SIZE,
            similarity_threshold=SIMILARITY_THRESHOLD,
            iou_threshold=TRACK_IOU_THRESHOLD,
            min_bbox_size=MIN_FACE_BBOX_SIZE,
            min_detection_score=MIN_DETECTION_SCORE,
            guest_prefix=f"GUEST_{camera_id}",
        )

        await asyncio.to_thread(
            state.track_manager.load_known_embeddings
        )

        await websocket.send_json({
            "type": "ready",
            "camera_id": camera_id,
            "connection_id": connection_id,
        })

        # Khởi tạo reader task và vòng receive như code hiện tại.
        # Mọi worker channel sử dụng connection_id.

    except WebSocketDisconnect:
        pass

    finally:
        await cleanup_camera_connection(
            redis=r,
            pubsub=pubsub,
            camera_id=camera_id,
            connection_id=connection_id,
        )
~~~

### 15.6 Frame metadata đề xuất

~~~python
if "bytes" in msg:
    data = msg["bytes"]

    if data:
        state.latest_jpeg = bytes(data)
        state.last_frame_time = time.time()

        await renew_camera_lease(
            redis=r,
            camera_id=camera_id,
            connection_id=connection_id,
            ttl_seconds=15,
        )

        opeid = str(uuid.uuid4())

        meta_dict = {
            "opeid": opeid,
            "camera_id": camera_id,
            "connection_id": connection_id,
            "timestamp": datetime.now().isoformat(),
        }

        meta_json = json.dumps(meta_dict).encode("utf-8")
        meta_len = len(meta_json).to_bytes(4, byteorder="big")
        packed_payload = meta_len + meta_json + bytes(data)

        await r.lpush("camera_frames_v2", packed_payload)
        await r.ltrim("camera_frames_v2", 0, 50)
~~~

### 15.7 Cleanup

~~~python
async def cleanup_camera_connection(
    redis,
    pubsub,
    camera_id: str,
    connection_id: str,
):
    with CONNECTION_STATES_LOCK:
        state = CONNECTION_STATES.pop(connection_id, None)

    if state and state.track_manager:
        # Thực hiện cleanup tracker nếu class hỗ trợ.
        state.track_manager = None

    await pubsub.unsubscribe()
    await pubsub.close()

    await release_camera_lease_if_owner(
        redis=redis,
        camera_id=camera_id,
        connection_id=connection_id,
    )
~~~

### 15.8 Danh sách camera

~~~python
@router.get("/api/cameras")
async def api_cameras(authorization: str | None = Header(default=None)):
    user = get_user_from_token(authorization)
    cameras = list_cameras_allowed_for_user(user)
    r = await get_redis()
    result = []

    for camera in cameras:
        lease_key = f"camera:presence:{camera['camera_id']}"
        connection_id = await r.get(lease_key)

        result.append({
            "camera_id": camera["camera_id"],
            "display_name": camera["display_name"],
            "active": connection_id is not None,
            "connection_id": (
                connection_id.decode("utf-8")
                if connection_id
                else None
            ),
            "last_seen_at": camera["last_seen_at"],
        })

    return {
        "status": "success",
        "cameras": result,
    }
~~~

Danh sách lấy từ database, presence lấy từ Redis. Không duyệt toàn bộ ConnectionState để tạo camera cards.

## 16. Code AI worker đề xuất

~~~python
opeid = data.get("opeid")
camera_id = data.get("camera_id")
connection_id = data.get("connection_id")

if not camera_id or not connection_id:
    logger.warning(
        "Received frame without camera_id or connection_id. Skipping."
    )
    continue

# Detect và embedding giữ nguyên.

pubsub_channel = f"worker_results_{connection_id}"

payload = {
    "opeid": opeid,
    "camera_id": camera_id,
    "connection_id": connection_id,
    "timestamp": data.get("timestamp"),
    "face_records": face_records,
    "frame_size": {
        "width": frame.shape[1],
        "height": frame.shape[0],
    },
}

redis_client.publish(
    pubsub_channel,
    json.dumps(payload),
)
~~~

## 17. Code frontend đề xuất

### 17.1 API service

File: frontend/src/services/api.js.

~~~js
export async function resolveDeviceIdentity() {
  const response = await fetch(
    API_BASE_URL + "/api/device/identity",
    {
      method: "POST",
      credentials: "include",
    },
  );

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      data.detail || "Không thể nhận diện thiết bị",
    );
  }

  return response.json();
}
~~~

### 17.2 Dashboard

File: frontend/src/app/page.jsx.

Xóa:

~~~jsx
const sessionIdRef = useRef(null);

if (!sessionIdRef.current && typeof window !== "undefined") {
  sessionIdRef.current =
    "camera_" + Math.random().toString(36).substring(2, 9);
}

const sessionId = sessionIdRef.current || "default";
~~~

Thay bằng:

~~~jsx
const [cameraIdentity, setCameraIdentity] = useState(null);
const [identityError, setIdentityError] = useState("");

useEffect(() => {
  let cancelled = false;

  async function loadIdentity() {
    try {
      const data = await resolveDeviceIdentity();

      if (!cancelled) {
        setCameraIdentity(data);
      }
    } catch (error) {
      if (!cancelled) {
        setIdentityError(
          error instanceof Error
            ? error.message
            : "Không thể nhận diện thiết bị",
        );
      }
    }
  }

  loadIdentity();

  return () => {
    cancelled = true;
  };
}, []);
~~~

Không render CameraStream khi chưa có identity:

~~~jsx
if (identityError) {
  return <DeviceIdentityError message={identityError} />;
}

if (!cameraIdentity) {
  return <DeviceIdentityLoading />;
}
~~~

Render:

~~~jsx
<CameraStream
  cameraId={cameraIdentity.camera_id}
  highlightedTrackId={highlightedTrackId}
  framed={false}
  fullHeight={true}
  onCustomersChange={handleCustomersChange}
/>
~~~

### 17.3 CameraStream

Đổi prop:

~~~jsx
export default function CameraStream({
  cameraId,
  highlightedTrackId = null,
  framed = true,
  compact = false,
  fullHeight = false,
  onCustomersChange = null,
}) {
  const camera = useCamera(cameraId);
~~~

### 17.4 useCamera

~~~js
function getWsUrl(cameraId) {
  const protocol =
    window.location.protocol === "https:" ? "wss:" : "ws:";

  let host = "localhost:8000";
  const baseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_HOST;

  if (baseUrl) {
    try {
      const url = baseUrl.includes("://")
        ? new URL(baseUrl)
        : new URL("http://" + baseUrl);
      host = url.host;
    } catch (_) {
      host = baseUrl.replace(/^https?:\/\//, "");
    }
  }

  return (
    protocol +
    "//" +
    host +
    "/ws/" +
    encodeURIComponent(cameraId)
  );
}
~~~

State mới:

~~~js
const [serverReady, setServerReady] = useState(false);
const [connectionId, setConnectionId] = useState(null);
~~~

Message ready:

~~~js
ws.onmessage = async (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "ready") {
    setConnectionId(data.connection_id);
    setServerReady(true);
    setWsStatus("live");
    return;
  }

  // Giữ nguyên xử lý customers và WebRTC hiện tại.
};
~~~

Chỉ gửi frame khi server ready:

~~~js
const sendFrame = useCallback(() => {
  if (!serverReady) return;
  if (sendingRef.current) return;

  const ws = wsRef.current;

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return;
  }

  // Phần capture và ws.send(blob/arrayBuffer) giữ nguyên.
}, [serverReady]);
~~~

Khi close:

~~~js
ws.onclose = () => {
  if (!mountedRef.current) return;

  setServerReady(false);
  setConnectionId(null);
  setWsStatus("disconnected");

  reconnectRef.current = setTimeout(
    connectWs,
    RECONNECT_DELAY_MS,
  );
};
~~~

Cookie tự đi trong handshake. WebSocket constructor không cần và không có credentials: include.

### 17.5 Camera management service

~~~js
export async function fetchCameras() {
  const response = await fetch(
    API_BASE_URL + "/api/cameras",
    {
      headers: getAuthHeaders(),
      credentials: "include",
    },
  );

  if (!response.ok) {
    throw new Error("Không thể tải danh sách camera");
  }

  return response.json();
}
~~~

Màn camera đổi từ data.sessions sang data.cameras.

## 18. Observer/admin flow mới

Observer không sử dụng publisher device cookie. Observer phải dùng tài khoản quản trị/moderator và quyền camera.

Luồng:

~~~text
Admin gọi GET /api/cameras với login token
    ↓
Chọn camera_id
    ↓
Mở /ws/observe/{camera_id}
    ↓
Backend xác thực admin/moderator
    ↓
Backend kiểm tra user có quyền xem camera
    ↓
Backend đọc presence lease để lấy active connection_id
    ↓
Subscribe signaling/result của active connection
~~~

Nếu publisher reconnect:

1. camera_id không đổi.
2. presence lease đổi sang connection_id mới.
3. Observer layer phải rebind sang connection mới hoặc dùng một bridge channel ổn định theo camera_id.

Hai lựa chọn:

### Lựa chọn A: Bridge channel theo camera_id

Publisher/master nhận result theo connection_id, sau khi xác minh hợp lệ thì publish bản đã kiểm tra lên:

~~~text
camera_updates:{camera_id}
~~~

Observer subscribe camera_updates:{camera_id}.

Đây là lựa chọn dễ duy trì nhất.

### Lựa chọn B: Observer theo dõi presence lease

Observer phát hiện connection_id thay đổi rồi unsubscribe channel cũ và subscribe channel mới.

Khuyến nghị chọn A.

WebRTC signaling có thể dùng:

~~~text
publisher_signaling:{connection_id}
observer_signaling:{camera_id}:{observer_id}
~~~

hoặc bridge ở master. Cần giữ admin_id hiện có để phân biệt peer connection.

## 19. Luồng disconnect và reconnect

### 19.1 Disconnect

~~~text
WebSocket conn_a đóng
    ↓
Cancel reader task
    ↓
Unsubscribe Redis
    ↓
Đóng WebRTC peer connections
    ↓
Xóa ConnectionState[conn_a]
    ↓
Release lease nếu lease vẫn thuộc conn_a
    ↓
Camera cam_7f1c9a vẫn còn trong database
    ↓
Màn quản lý hiển thị Idle
~~~

### 19.2 Reconnect

~~~text
Frontend gọi lại /api/device/identity
    ↓
Browser gửi cookie cũ
    ↓
Backend trả camera_id cũ
    ↓
Frontend mở /ws/{camera_id}
    ↓
Backend tạo conn_b
    ↓
camera_id không đổi
connection_id thay đổi
~~~

### 19.3 Kết quả AI đến trễ

Nếu worker trả result của conn_a sau khi conn_a đã đóng:

~~~text
Master không tìm thấy ConnectionState[conn_a]
hoặc lease không còn thuộc conn_a
    ↓
Bỏ result
~~~

Không được đưa result cũ vào conn_b.

## 20. Mất cookie

Nếu cookie bị xóa, backend không có dữ liệu để tự chứng minh browser này là camera cũ.

### 20.1 Hành vi đơn giản

Không có cookie → tạo camera mới.

Nhược điểm: xóa cookie tạo duplicate camera.

### 20.2 Hành vi production khuyến nghị

Admin tạo pairing code một lần:

~~~text
CAMERA: cam_7f1c9a
PAIRING CODE: 483921
TTL: 10 phút
MAX USE: 1
~~~

Thiết bị nhập code:

~~~text
POST /api/device/enrollments/claim
~~~

Backend:

1. Kiểm tra code.
2. Gắn credential mới vào camera cũ.
3. Thu hồi credential cũ nếu cần.
4. Set-Cookie mới.
5. Trả camera_id cũ.

Không cần đăng nhập tài khoản trên thiết bị camera.

## 21. Bảo mật

### 21.1 Camera ID không phải secret

Biết camera_id không được phép kết nối nếu không có device_token hợp lệ.

### 21.2 Token

- Sinh bằng secrets.token_urlsafe ít nhất 32 bytes entropy.
- Chỉ lưu hash.
- Có revoke.
- Có last_used_at.
- Có thể rotate.

### 21.3 Cookie

- HttpOnly.
- Secure.
- Path=/.
- SameSite phù hợp deployment.
- Không đặt token vào localStorage.
- Không đưa token dài hạn vào query string.

### 21.4 WebSocket

- Kiểm tra Origin allowlist.
- Xác thực trước accept.
- Chỉ một publisher mỗi camera.
- Rate-limit handshake và enrollment.
- Giới hạn kích thước frame.
- Timeout connection không gửi heartbeat.

### 21.5 REST/CORS

Frontend cross-origin phải dùng:

~~~js
credentials: "include"
~~~

Backend hiện đã có allow_credentials=True và allowlist origin cụ thể. Không dùng Access-Control-Allow-Origin: * cùng credentials.

### 21.6 Observer

- /api/cameras cần login token.
- /ws/observe/{camera_id} cần xác thực admin/moderator.
- Enforce users.cameras/permission ở backend, không chỉ frontend.

### 21.7 Các vấn đề auth hiện hữu ngoài phạm vi chính

Code hiện dùng:

- SHA-256 trực tiếp cho password.
- ACTIVE_SESSIONS trong RAM.
- Login token trong localStorage.

Đây là các hạng mục nên harden riêng:

- Argon2/bcrypt cho password.
- Session store bền vững hoặc signed token.
- HttpOnly login session cookie.

Không bắt buộc phải hoàn tất cùng Camera ID migration, nhưng không nên xem Camera ID là cơ chế phân quyền.

## 22. Migration không downtime

### Giai đoạn 1: Schema

1. Thêm cameras.
2. Thêm camera_device_credentials.
3. Thêm connection_id nullable vào recognize_logs.
4. Thêm helper DB cho SQLite và PostgreSQL.

Không thay đổi luồng cũ.

### Giai đoạn 2: Identity bootstrap

1. Thêm /api/device/identity.
2. Thêm cookie config.
3. Thêm resolveDeviceIdentity frontend.
4. Log enrollment và resolve.

### Giai đoạn 3: Frontend

1. Xóa Math.random session ID.
2. Chờ identity trước CameraStream.
3. Đổi prop sessionId thành cameraId.
4. Giữ URL /ws/{cameraId} để giảm thay đổi.

### Giai đoạn 4: Dual metadata

1. Thêm connection_id ở master.
2. Gửi camera_id và connection_id sang worker.
3. Worker trả cả hai.
4. Trong giai đoạn tương thích, worker có thể fallback camera_id nếu thiếu connection_id, nhưng cần xóa fallback sau rollout.

### Giai đoạn 5: State và Redis

1. Tạo ConnectionState.
2. Result channel theo connection_id.
3. Presence lease theo camera_id.
4. Cleanup compare-and-delete.
5. Ready message.

### Giai đoạn 6: Camera management

1. Thêm GET /api/cameras.
2. Màn quản lý đọc database + Redis.
3. Observer dùng camera_id cố định.
4. Thêm bridge camera_updates:{camera_id}.
5. Enforce permission.

### Giai đoạn 7: Retire legacy

1. Dừng /api/active_sessions.
2. Xóa CAMERA_STATES làm catalog.
3. Xóa session_id naming ở frontend.
4. Xóa legacy result channel.
5. Cập nhật docs.

### Dữ liệu cũ

Các camera_xxxxx cũ không thể tự động map chính xác về thiết bị vật lý.

Xử lý:

- CAMERA_STATES là RAM: restart backend sẽ xóa.
- recognize_logs cũ: giữ camera_id cũ như legacy.
- Không tự đoán mapping.
- Nếu có thông tin vận hành, admin map thủ công.

## 23. Kiểm thử

### 23.1 Identity REST

- Không cookie → tạo camera và Set-Cookie.
- Cookie hợp lệ → trả camera cũ.
- Cookie invalid → không giả danh camera.
- Cookie revoked → từ chối và yêu cầu re-enroll.
- Hai request đồng thời → không tạo hai camera ngoài ý muốn.

### 23.2 Browser lifecycle

- Refresh giữ camera_id.
- Đóng/mở browser giữ camera_id.
- Restart máy giữ camera_id.
- Incognito tạo identity riêng hoặc yêu cầu pairing.
- Xóa cookie kích hoạt flow recovery.

### 23.3 WebSocket handshake

- Origin hợp lệ + cookie hợp lệ → 101.
- Thiếu cookie → handshake bị từ chối.
- Cookie CAM-A nhưng URL CAM-B → từ chối.
- Token revoked → từ chối.
- WSS gửi Secure cookie.

### 23.4 Connection

- Mỗi reconnect có connection_id mới.
- camera_id không đổi.
- Hai tab không cùng publish.
- Takeover hoạt động.
- Connection cũ không xóa lease connection mới.

### 23.5 Worker

- Payload có cả hai ID.
- Result publish theo connection_id.
- Result đến trễ bị bỏ.
- recognize_logs ghi Camera ID cố định.

### 23.6 Presence

- Frame/heartbeat renew TTL.
- Mất mạng chuyển Idle trong khoảng 15 giây.
- Disconnect sạch chuyển Idle sớm.
- Redis restart không tạo camera mới; chỉ mất presence tạm.

### 23.7 Observer

- Admin xem được camera được phép.
- Moderator chỉ xem camera được gán.
- Publisher reconnect không tạo card mới.
- Observer tự theo connection mới.
- WebRTC signaling không lẫn camera.

### 23.8 Regression

- JPEG binary streaming giữ nguyên.
- Bounding boxes giữ nguyên.
- Customer payload giữ nguyên.
- WebRTC offer/answer/ICE giữ nguyên.
- Camera selector MediaDeviceInfo.deviceId vẫn hoạt động.
- AI queue camera_frames_v2 vẫn hoạt động.

## 24. Acceptance criteria

Migration được xem là hoàn tất khi:

1. Một browser profile luôn nhận cùng camera_id nếu cookie còn tồn tại.
2. Không cần tài khoản để publisher được nhận diện.
3. Refresh không tạo camera card mới.
4. Reconnect không tạo camera card mới.
5. Backend restart không làm mất catalog camera.
6. Mỗi connection có connection_id riêng.
7. Camera ID và Connection ID xuất hiện đúng trong log.
8. Camera chuyển Idle trong thời gian TTL.
9. State cũ được cleanup.
10. Kết quả worker cũ không lọt sang connection mới.
11. Cookie HttpOnly được gửi trong REST và WebSocket handshake.
12. Camera ID trong URL không đủ để giả danh camera.
13. Observer được xác thực và phân quyền.
14. Xóa cookie có flow pairing/recovery rõ ràng.

## 25. Bảng đối chiếu cuối cùng

| Thành phần | Luồng cũ | Luồng mới |
|---|---|---|
| Cấp danh tính | Frontend Math.random | Backend resolve device_token và trả camera_id |
| Giá trị truyền vào CameraStream | sessionId ngẫu nhiên | cameraId cố định |
| URL WebSocket | /ws/{sessionId} | /ws/{cameraId} |
| Trước accept | Không xác thực, accept ngay | Kiểm tra Origin, cookie và camera_id |
| Connection handle | Không tách riêng | Sinh connection_id tạm |
| Chống kết nối trùng | Không có | Acquire Redis lease bằng connection_id |
| Nâng cấp giao thức | Xảy ra trước kiểm tra nghiệp vụ | Chỉ gọi accept sau khi xác thực và giữ lease thành công |
| State realtime | CAMERA_STATES[sessionId] | Tạo CONNECTION_STATES[connection_id] sau HTTP 101 |
| Worker result | worker_results_{sessionId} | worker_results_{connection_id} |
| Metadata | camera_id = sessionId | camera_id cố định + connection_id tạm |
| Danh sách camera | Duyệt CAMERA_STATES trong RAM | Đọc camera từ DB và Live/Idle từ Redis |

## 26. Quyết định mặc định đề xuất

| Hạng mục | Quyết định |
|---|---|
| Camera ID | Opaque UUID có prefix cam_ |
| Cookie | device_token, HttpOnly, Secure, Path=/ |
| Cookie production | SameSite=Lax trên checkinface.me |
| Identity API | POST /api/device/identity resolve-or-create |
| Publisher WS | Giữ /ws/{camera_id} và xác thực cookie |
| Connection ID | UUID mới mỗi handshake |
| Single publisher | Có, Redis SET NX EX |
| Presence TTL | 15 giây |
| Renew | 5 giây hoặc mỗi frame |
| Worker channel | worker_results_{connection_id} |
| Observer channel | camera_updates:{camera_id} bridge |
| Camera catalog | Database |
| Live/Idle | Redis presence |
| Cookie mất | Pairing code để khôi phục |
| Legacy logs | Giữ nguyên, không tự map |

## 27. File dự kiến thay đổi khi triển khai

~~~text
backend/app/db/connection.py
    Thêm schema và repository camera/credential.

backend/app/api/routes.py
    Identity API, WebSocket auth, ConnectionState,
    presence lease, cleanup, camera list và observer.

backend/app/ai_worker.py
    Nhận connection_id và publish result theo connection.

frontend/src/services/api.js
    resolveDeviceIdentity và fetchCameras.

frontend/src/app/page.jsx
    Bỏ Math.random, bootstrap identity.

frontend/src/components/CameraStream.jsx
    Đổi sessionId thành cameraId.

frontend/src/hooks/useCamera.js
    URL theo cameraId, ready handshake và reconnect.

frontend/src/hooks/useCameraObserver.js
    Observe theo cameraId ổn định.

frontend/src/app/camera/page.jsx
    Danh sách cameras thay cho sessions.

docs/api_reference.md
docs/database_schema.md
docs/system_architecture.md
docs/frontend_architecture.md
    Cập nhật tài liệu sau rollout.
~~~

## 28. Kết luận

Vấn đề không nằm ở WebSocket transport. Vấn đề nằm ở việc hệ thống dùng một chuỗi random của frontend làm đồng thời Camera ID và WebSocket session ID.

Giải pháp:

~~~text
Camera identity:
    Database + device credential cookie

Connection isolation:
    connection_id riêng mỗi WebSocket

Live/Idle:
    Redis lease có TTL

Realtime result:
    channel theo connection_id

History/UI:
    camera_id cố định

Disconnect:
    xóa connection state, giữ camera record
~~~

Cookie HttpOnly không làm thay đổi cơ chế gửi JPEG, nhận JSON hoặc WebRTC signaling. Cookie chỉ xuất hiện trong HTTP request và WebSocket opening handshake để backend xác định browser này thuộc camera nào.

export async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
  }
  return response;
}

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000");

function getAuthHeaders() {
  const headers = {};
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return headers;
}

export async function postLogin(username, password) {
  const response = await apiFetch(`${API_BASE_URL}/api/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Login failed");
  }
  return response.json();
}

let identityRequest = null;

export function resolveDeviceIdentity() {
  if (!identityRequest) {
    identityRequest = apiFetch(`${API_BASE_URL}/api/device/identity`, {
      method: "POST",
      credentials: "include",
    })
      .then(async (response) => {
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.detail || "Không thể nhận diện thiết bị");
        }
        return response.json();
      })
      .finally(() => {
        identityRequest = null;
      });
  }
  return identityRequest;
}

export async function fetchCustomerInfo(cameraId = null) {
  const url = cameraId
    ? `${API_BASE_URL}/api/customer_info?camera_id=${encodeURIComponent(cameraId)}`
    : `${API_BASE_URL}/api/customer_info`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function fetchCustomersOverview(cameraId = null) {
  const url = cameraId
    ? `${API_BASE_URL}/api/customers_overview?camera_id=${encodeURIComponent(cameraId)}`
    : `${API_BASE_URL}/api/customers_overview`;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function postCheckIn(cameraId = null) {
  const url = cameraId
    ? `${API_BASE_URL}/api/check_in?camera_id=${encodeURIComponent(cameraId)}`
    : `${API_BASE_URL}/api/check_in`;
  const response = await apiFetch(url, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}

export async function postCheckInById(customerId) {
  const response = await apiFetch(`${API_BASE_URL}/api/check_in/${customerId}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}

export async function putCustomerProfile(payload) {
  const response = await apiFetch(`${API_BASE_URL}/api/customer_profile`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Request failed");
  }
  return response.json();
}

export async function fetchAllCustomers() {
  const response = await apiFetch(`${API_BASE_URL}/api/customers`, {
    headers: {
      ...getAuthHeaders(),
    },
  });
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function fetchCustomerProfileById(customerId) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/customer_profile_by_id/${encodeURIComponent(customerId)}`,
    {
      headers: {
        ...getAuthHeaders(),
      },
    },
  );
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function fetchCameras() {
  const response = await apiFetch(`${API_BASE_URL}/api/cameras`, {
    headers: getAuthHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Không thể tải danh sách camera");
  }
  return response.json();
}

export async function renameCamera(cameraId, displayName) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/cameras/${encodeURIComponent(cameraId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ display_name: displayName }),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể đổi tên camera");
  }
  return response.json();
}

export async function deleteCamera(cameraId) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/cameras/${encodeURIComponent(cameraId)}`,
    {
      method: "DELETE",
      headers: getAuthHeaders(),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể xóa camera");
  }
  return response.json();
}

export async function disconnectCamera(cameraId) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/cameras/${encodeURIComponent(cameraId)}/disconnect`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể ngắt phiên phát camera");
  }
  return response.json();
}

export async function fetchUsers() {
  const response = await apiFetch(`${API_BASE_URL}/api/users`, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error("Không thể tải danh sách tài khoản");
  }
  return response.json();
}

export async function createModerator(username, password) {
  const response = await apiFetch(`${API_BASE_URL}/api/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể tạo moderator");
  }
  return response.json();
}

export async function updateModerator(username, payload) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/users/${encodeURIComponent(username)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể cập nhật moderator");
  }
  return response.json();
}

export async function deleteModerator(username) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/users/${encodeURIComponent(username)}`,
    { method: "DELETE", headers: getAuthHeaders() },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể xóa moderator");
  }
  return response.json();
}

export async function updateCameraPermissions(username, cameraIds) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/users/${encodeURIComponent(username)}/camera_permissions`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ camera_ids: cameraIds }),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail?.message || data.detail || "Không thể lưu phân quyền");
  }
  return response.json();
}

export async function claimDeviceEnrollment(code) {
  const response = await apiFetch(
    `${API_BASE_URL}/api/device/enrollments/claim`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Mã ghép nối không hợp lệ");
  }
  return response.json();
}

export async function createDeviceEnrollment(cameraId) {
  const response = await apiFetch(`${API_BASE_URL}/api/device/enrollments`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders() },
    body: JSON.stringify({ camera_id: cameraId, revoke_existing: true }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể tạo mã ghép nối");
  }
  return response.json();
}

export async function fetchSettings() {
  const response = await apiFetch(`${API_BASE_URL}/api/settings`, {
    headers: {
      ...getAuthHeaders(),
    },
  });
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function updateSettings(payload) {
  const response = await apiFetch(`${API_BASE_URL}/api/settings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Request failed");
  }
  return response.json();
}

export async function getRecognizeLogs(params = {}) {
  const query = new URLSearchParams();
  if (params.startDate) query.append("start_date", params.startDate);
  if (params.endDate) query.append("end_date", params.endDate);
  if (params.cameraId && params.cameraId !== "all") query.append("camera_id", params.cameraId);
  if (params.customerType && params.customerType !== "all") query.append("customer_type", params.customerType);
  if (params.search) query.append("search", params.search);
  if (params.page) query.append("page", params.page);
  if (params.limit) query.append("limit", params.limit);

  const response = await apiFetch(`${API_BASE_URL}/api/logs?${query.toString()}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể nạp lịch sử nhận diện");
  }
  return response.json();
}

export async function exportRecognizeLogsCsv(params = {}) {
  const query = new URLSearchParams();
  if (params.startDate) query.append("start_date", params.startDate);
  if (params.endDate) query.append("end_date", params.endDate);
  if (params.cameraId && params.cameraId !== "all") query.append("camera_id", params.cameraId);
  if (params.customerType && params.customerType !== "all") query.append("customer_type", params.customerType);
  if (params.search) query.append("search", params.search);

  const response = await apiFetch(`${API_BASE_URL}/api/logs/export?${query.toString()}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!response.ok) {
    throw new Error("Xuất file CSV thất bại");
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nhat_ky_nhan_dien_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  a.remove();
}

export async function fetchReportsData(params = {}) {
  const query = new URLSearchParams();
  if (params.startDate) query.append("start_date", params.startDate);
  if (params.endDate) query.append("end_date", params.endDate);
  if (params.cameraId && params.cameraId !== "all") query.append("camera_id", params.cameraId);

  const response = await apiFetch(`${API_BASE_URL}/api/reports?${query.toString()}`, {
    headers: { ...getAuthHeaders() },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể nạp dữ liệu báo cáo thống kê");
  }
  return response.json();
}



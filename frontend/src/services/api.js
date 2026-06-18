export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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
  const response = await fetch(`${API_BASE_URL}/api/login`, {
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

export async function fetchCustomerInfo() {
  const response = await fetch(`${API_BASE_URL}/api/customer_info`);
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function fetchCustomersOverview() {
  const response = await fetch(`${API_BASE_URL}/api/customers_overview`);
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function postCheckIn() {
  const response = await fetch(`${API_BASE_URL}/api/check_in`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}

export async function postCheckInById(customerId) {
  const response = await fetch(`${API_BASE_URL}/api/check_in/${customerId}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}

export async function putCustomerProfile(payload) {
  const response = await fetch(`${API_BASE_URL}/api/customer_profile`, {
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
  const response = await fetch(`${API_BASE_URL}/api/customers`, {
    headers: {
      ...getAuthHeaders(),
    }
  });
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}

export async function fetchCustomerProfileById(customerId) {
  const response = await fetch(`${API_BASE_URL}/api/customer_profile_by_id/${encodeURIComponent(customerId)}`, {
    headers: {
      ...getAuthHeaders(),
    }
  });
  if (!response.ok) {
    throw new Error("Network error");
  }
  return response.json();
}
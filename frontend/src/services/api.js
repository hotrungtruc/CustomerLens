export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json();
}

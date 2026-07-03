import re

with open('src/services/api.js', 'r', encoding='utf-8') as f:
    content = f.read()

api_fetch_code = """
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
"""

if 'apiFetch' not in content:
    content = content.replace('export const API_BASE_URL', api_fetch_code + '\\nexport const API_BASE_URL')
    content = content.replace(' await fetch(', ' await apiFetch(')
    content = content.replace(' identityRequest = fetch(', ' identityRequest = apiFetch(')

with open('src/services/api.js', 'w', encoding='utf-8') as f:
    f.write(content)

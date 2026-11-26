/**
 * Parse an API response, throwing an Error whose message players can read.
 *
 * When the backend isn't running, the development proxy (or Tailscale Funnel)
 * answers with a plain-text error page instead of JSON; say so rather than
 * showing a JSON syntax error.
 */
export async function readJson(res) {
  let body;
  try {
    body = await res.json();
  } catch {
    const error = new Error(
      res.ok ? '後端回傳了無法解讀的資料' : `連不上後端伺服器（HTTP ${res.status}），請確認後端有啟動`
    );
    error.status = res.status;
    throw error;
  }
  if (!res.ok) {
    const error = new Error(body.detail || res.statusText);
    error.status = res.status;
    throw error;
  }
  return body;
}

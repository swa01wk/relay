// Calls to the Relay gateway. Errors carry the gateway's own message.
export class ApiError extends Error {
  constructor(status, message, { reauth = false, retryAfter = null } = {}) {
    super(message);
    this.status = status;
    // The gateway wants the password again before this change (X-Relay-Reauth: required).
    this.reauth = reauth;
    this.retryAfter = retryAfter;
  }
}

export async function request(gateway, path, { method = "GET", token, body } = {}) {
  let response;
  try {
    response = await fetch(`${gateway}${path}`, {
      method,
      headers: {
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiError(0, `cannot reach the Relay gateway at ${gateway} (${error?.cause?.code ?? error.message})`);
  }
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // not JSON; fall through with the status
  }
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `request failed (${response.status})`;
    throw new ApiError(response.status, detail, {
      reauth: response.headers.get("x-relay-reauth") === "required",
      retryAfter: response.headers.get("retry-after"),
    });
  }
  return data;
}

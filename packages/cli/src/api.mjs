// Calls to the Relay gateway. Errors carry the gateway's own message.
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
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
    throw new ApiError(response.status, detail);
  }
  return data;
}

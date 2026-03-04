export async function apiFetch(
  path: string,
  options: RequestInit = {},
  authToken?: string,
): Promise<Response> {
  const headers = new Headers(options.headers)
  if (!headers.has("content-type") && options.method && options.method !== "GET") {
    headers.set("content-type", "application/json")
  }
  if (authToken) {
    headers.set("x-auth", authToken)
  }
  return fetch(path, { ...options, headers })
}

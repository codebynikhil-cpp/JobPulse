export async function request<T = unknown>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T | null> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
    cache: "no-store",
  });
  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    window.location.assign("/login");
    throw new Error("Your session expired. Please sign in again.");
  }
  if (!response.ok) {
    const body: { detail?: unknown } = await response.json().catch(() => ({}));
    if (typeof body.detail === "string") throw new Error(body.detail);
    if (Array.isArray(body.detail)) {
      const messages = body.detail.map((item: unknown) => {
        if (
          typeof item === "object" &&
          item !== null &&
          "msg" in item &&
          typeof item.msg === "string"
        )
          return item.msg;
        return "Check the supplied values.";
      });
      throw new Error(messages.join(" "));
    }
    throw new Error("Unable to complete this request. Please retry.");
  }
  return response.status === 204 ? null : response.json();
}

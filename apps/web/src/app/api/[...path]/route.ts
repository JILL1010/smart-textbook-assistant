export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> }
) {
  const { path } = await context.params;
  const base = process.env.API_UPSTREAM_URL || "http://127.0.0.1:8081";
  const url = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, base);
  url.search = new URL(request.url).search;
  const headers = new Headers();
  for (const name of ["content-type", "range", "if-range"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const options: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      cache: "no-store",
      signal: request.signal,
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      options.body = request.body;
      options.duplex = "half";
    }
    const response = await fetch(url, options);
    const responseHeaders = new Headers(response.headers);
    for (const name of ["connection", "transfer-encoding", "content-encoding", "content-length"]) {
      responseHeaders.delete(name);
    }
    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "无法连接后端服务，请检查服务是否启动" }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as DELETE, proxy as HEAD };

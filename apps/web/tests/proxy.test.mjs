import assert from "node:assert/strict";
import fs from "node:fs";
import { test, afterEach } from "node:test";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/app/api/[...path]/route.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const handlers = {};
new Function("exports", code)(handlers);
const originalFetch = global.fetch;
const originalUpstream = process.env.API_UPSTREAM_URL;

afterEach(() => {
  global.fetch = originalFetch;
  if (originalUpstream === undefined) delete process.env.API_UPSTREAM_URL;
  else process.env.API_UPSTREAM_URL = originalUpstream;
});

test("runtime port and query reach upstream; audio ranges survive", async () => {
  process.env.API_UPSTREAM_URL = "http://127.0.0.1:18082";
  global.fetch = async (url, options) => {
    assert.equal(String(url), "http://127.0.0.1:18082/api/audio/demo.mp3?download=1");
    assert.equal(options.headers.get("range"), "bytes=0-2");
    return new Response("mp3", { status: 206, headers: { "Content-Range": "bytes 0-2/10" } });
  };
  const response = await handlers.GET(
    new Request("http://localhost:3000/api/audio/demo.mp3?download=1", { headers: { Range: "bytes=0-2" } }),
    { params: Promise.resolve({ path: ["audio", "demo.mp3"] }) }
  );
  assert.equal(response.status, 206);
  assert.equal(response.headers.get("content-range"), "bytes 0-2/10");
  assert.equal(await response.text(), "mp3");
});

test("multipart uploads stream without losing their boundary or contents", async () => {
  const form = new FormData();
  form.append("file", new Blob(["textbook"], { type: "application/pdf" }), "book.pdf");
  global.fetch = async (url, options) => {
    const forwarded = new Request(url, options);
    const uploaded = (await forwarded.formData()).get("file");
    assert.equal(uploaded.name, "book.pdf");
    assert.equal(await uploaded.text(), "textbook");
    return Response.json({ id: 1 });
  };
  const response = await handlers.POST(
    new Request("http://localhost:3000/api/upload", { method: "POST", body: form }),
    { params: Promise.resolve({ path: ["upload"] }) }
  );
  assert.deepEqual(await response.json(), { id: 1 });
});

test("backend upload limit errors remain actionable", async () => {
  global.fetch = async () => Response.json({ detail: "文件超过限额" }, { status: 413 });
  const response = await handlers.POST(
    new Request("http://localhost:3000/api/upload", { method: "POST", body: "large" }),
    { params: Promise.resolve({ path: ["upload"] }) }
  );
  assert.equal(response.status, 413);
  assert.equal((await response.json()).detail, "文件超过限额");
});

test("backend connection errors produce a useful 502", async () => {
  global.fetch = async () => { throw new Error("connection refused"); };
  const response = await handlers.GET(
    new Request("http://localhost:3000/api/health"),
    { params: Promise.resolve({ path: ["health"] }) }
  );
  assert.equal(response.status, 502);
  assert.match((await response.json()).detail, /后端服务/);
});

test("DELETE and HEAD preserve their method", async () => {
  for (const method of ["DELETE", "HEAD"]) {
    global.fetch = async (_, options) => {
      assert.equal(options.method, method);
      return new Response(null, { status: 204 });
    };
    const response = await handlers[method](
      new Request("http://localhost:3000/api/textbooks/1", { method }),
      { params: Promise.resolve({ path: ["textbooks", "1"] }) }
    );
    assert.equal(response.status, 204);
  }
});

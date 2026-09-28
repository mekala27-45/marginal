// Serves the static export the way GitHub Pages does: under the base path, with a trailing slash
// redirect, the 404 page, and byte range requests, which DuckDB-WASM uses to read the parquet
// marts a slice at a time. Python's http.server ignores Range, so the tests use this instead.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "out");
const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "/marginal";
const port = Number(process.env.MARGINAL_E2E_PORT ?? 4173);

if (!existsSync(join(root, "index.html"))) {
  console.error("out/index.html is missing: run `npm run build` first");
  process.exit(1);
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".wasm": "application/wasm",
  ".parquet": "application/vnd.apache.parquet",
};

function send404(res, head) {
  const page = join(root, "404.html");
  res.writeHead(404, { "Content-Type": TYPES[".html"] });
  if (head || !existsSync(page)) return res.end();
  createReadStream(page).pipe(res);
}

createServer((req, res) => {
  // GitHub Pages answers HEAD with a 503, so the tests see the same refusal here and the data
  // layer has to size a mart from the bundle or from a one byte range, never from HEAD.
  if (req.method === "HEAD") {
    res.writeHead(503);
    return res.end();
  }
  const head = false;
  if (req.method !== "GET") {
    res.writeHead(405, { Allow: "GET" });
    return res.end();
  }
  const url = new URL(req.url ?? "/", "http://localhost");
  let path = decodeURIComponent(url.pathname);
  if (base) {
    if (path === "/" || path === base) {
      res.writeHead(301, { Location: `${base}/` });
      return res.end();
    }
    if (!path.startsWith(`${base}/`)) return send404(res, head);
    path = path.slice(base.length);
  }
  let file = normalize(join(root, path));
  if (file !== root && !file.startsWith(root + sep)) return send404(res, head);
  if (existsSync(file) && statSync(file).isDirectory()) {
    if (!url.pathname.endsWith("/")) {
      res.writeHead(301, { Location: `${url.pathname}/${url.search}` });
      return res.end();
    }
    file = join(file, "index.html");
  }
  if (!existsSync(file) && existsSync(`${file}.html`)) file = `${file}.html`;
  if (!existsSync(file) || !statSync(file).isFile()) return send404(res, head);

  const size = statSync(file).size;
  const headers = {
    "Content-Type": TYPES[extname(file)] ?? "application/octet-stream",
    "Accept-Ranges": "bytes",
    "Cache-Control": "no-cache",
  };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  if (range && (range[1] || range[2])) {
    let start = range[1] ? Number(range[1]) : Math.max(size - Number(range[2]), 0);
    let end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
    if (start >= size || start > end) {
      res.writeHead(416, { ...headers, "Content-Range": `bytes */${size}` });
      return res.end();
    }
    start = Math.max(start, 0);
    end = Math.max(end, start);
    res.writeHead(206, { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
    if (head) return res.end();
    return createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(200, { ...headers, "Content-Length": size });
  if (head) return res.end();
  createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => {
  console.log(`serving out/ at http://127.0.0.1:${port}${base}/`);
});

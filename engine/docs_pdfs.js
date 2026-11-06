// PDF copies of README.md, docs/QUICKSTART.md and docs/MANUAL.md (run by engine/build_docs.py --pdfs).
// usage: node engine/docs_pdfs.js <out dir> <markdown file> [<markdown file> ...]
// Each Markdown file is rendered in headless Chromium (marked for the text, mermaid for the diagrams, both loaded from a
// pinned CDN version, so making the PDFs needs the internet; reading them does not) and printed to <out dir>/<name>.pdf.
// Links to other documents are printed as text with the PDF's name (no file:// addresses); <details> sections are printed open.
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const crypto = require("crypto");
// Each script is downloaded, checked against this sha256 and only then run; a changed file is refused.
const MARKED = { url: "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js",
                 sha256: "15fabce5b65898b32b03f5ed25e9f891a729ad4c0d6d877110a7744aa847a894" };
const MERMAID = { url: "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js",
                  sha256: "61b335a46df05a7ce1c98378f60e5f3e77a7fb608a1056997e8a649304a936d6" };

async function pinnedScript({ url, sha256 }) {
  let text;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    text = Buffer.from(await res.arrayBuffer());
  } catch (e) { throw new Error(`could not load ${url}: making the PDFs needs the internet (${e.message})`); }
  const got = crypto.createHash("sha256").update(text).digest("hex");
  if (got !== sha256) throw new Error(`${url} has sha256 ${got}, expected ${sha256}: refusing to run it`);
  return text.toString("utf8");
}

const CSS = `
  @page { size: A4; }
  body { font: 10.5pt/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1f2328; margin: 0; }
  h1, h2, h3, h4 { line-height: 1.25; margin: 1.4em 0 .5em; break-after: avoid; }
  h1 { font-size: 22pt; border-bottom: 1px solid #d0d7de; padding-bottom: .25em; margin-top: 0; }
  h2 { font-size: 15pt; border-bottom: 1px solid #d0d7de; padding-bottom: .2em; }
  h3 { font-size: 12pt; }
  p, ul, ol { margin: .5em 0; }
  code { font: 9pt ui-monospace, Menlo, Consolas, monospace; font-variant-ligatures: none; background: #eff1f3; padding: .1em .3em; border-radius: 3px; overflow-wrap: break-word; }
  pre { background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 6px; padding: 8px 10px; white-space: pre-wrap; overflow-wrap: break-word; }
  pre code { background: none; padding: 0; font-size: 7.6pt; }
  table { border-collapse: collapse; width: 100%; margin: .8em 0; font-size: 8.8pt; }
  th, td { border: 1px solid #d0d7de; padding: 4px 6px; vertical-align: top; overflow-wrap: break-word; text-align: left; }
  th { background: #f0f3f6; }
  tr { break-inside: avoid; }
  img { max-width: 100%; }
  blockquote { margin: .6em 0; padding: 0 1em; color: #59636e; border-left: 3px solid #d0d7de; }
  a { color: #0550ae; text-decoration: none; }
  details { margin: .5em 0; } summary { font-weight: 600; }
  .mermaid { text-align: center; margin: .8em 0; break-inside: avoid; }
  .mermaid svg { max-width: 100%; max-height: 225mm; width: auto; height: auto; }
`;

function shell(title) {
  return `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><style>${CSS}</style></head><body><main id="doc"></main></body></html>`;
}

async function render(browser, mdPath, outDir, names) {
  const dir = path.dirname(mdPath);
  const name = path.basename(mdPath, ".md");
  const text = fs.readFileSync(mdPath, "utf8");
  const tmp = path.join(dir, `.${name}.pdf-render.html`);       // beside the Markdown so relative images resolve
  fs.writeFileSync(tmp, shell(name));
  const page = await browser.newPage();
  try {
    await page.goto("file://" + tmp);
    for (const script of [MARKED, MERMAID]) await page.addScriptTag({ content: await pinnedScript(script) });
    const diagrams = await page.evaluate(async ([md, pdfNames]) => {
      const html = marked.parse(md, { gfm: true });
      const doc = document.getElementById("doc");
      doc.innerHTML = html;
      doc.querySelectorAll("pre > code.language-mermaid").forEach((code) => {
        const d = document.createElement("div");
        d.className = "mermaid";
        d.textContent = code.textContent;
        code.parentElement.replaceWith(d);
      });
      // A relative link would be printed as an absolute file:// address of the machine that made the PDF (wrong on any other
      // machine, and it would leak a local path). So only web and in-document links stay links; a link to another document
      // becomes plain text followed by that document's PDF name, and any other relative link becomes plain text.
      doc.querySelectorAll("a[href]").forEach((a) => {
        const href = a.getAttribute("href");
        if (/^(https?:|mailto:|#)/i.test(href)) { return; }
        const m = href.match(/^(?:\.\/|docs\/)?([A-Za-z]+)\.md(#.*)?$/);
        const span = document.createElement("span");
        span.textContent = a.textContent + (m && pdfNames.includes(m[1]) ? ` (${m[1]}.pdf)` : "");
        a.replaceWith(span);
      });
      doc.querySelectorAll("details").forEach((d) => { d.open = true; });
      mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict", flowchart: { htmlLabels: true } });
      const nodes = doc.querySelectorAll(".mermaid");
      await mermaid.run({ nodes });
      return [nodes.length, doc.querySelectorAll(".mermaid svg").length, doc.querySelectorAll("img").length];
    }, [text, names]);
    if (diagrams[0] !== diagrams[1]) { throw new Error(`${name}: ${diagrams[0]} diagrams, ${diagrams[1]} rendered`); }
    await page.evaluate(() => Promise.all([...document.images].map((i) => i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; }))));
    const broken = await page.evaluate(() => [...document.images].filter((i) => !i.naturalWidth).map((i) => i.getAttribute("src")));
    if (broken.length) { throw new Error(`${name}: images did not load: ${broken}`); }
    const out = path.join(outDir, name + ".pdf");
    await page.pdf({
      path: out, format: "A4", printBackground: true, displayHeaderFooter: true,
      margin: { top: "18mm", bottom: "18mm", left: "16mm", right: "16mm" },
      headerTemplate: `<div style="font:7pt sans-serif;color:#6e7781;width:100%;padding:0 16mm;">sd-forge: ${name}</div>`,
      footerTemplate: `<div style="font:7pt sans-serif;color:#6e7781;width:100%;text-align:right;padding:0 16mm;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
    });
    console.log(`${out}: ${diagrams[0]} diagrams, ${diagrams[2]} images`);
  } finally {
    await page.close();
    fs.rmSync(tmp, { force: true });
  }
}

(async () => {
  const [outDir, ...files] = process.argv.slice(2);
  if (!outDir || !files.length) { console.error("usage: node engine/docs_pdfs.js <out dir> <markdown file>..."); process.exit(2); }
  fs.mkdirSync(outDir, { recursive: true });
  const names = files.map((f) => path.basename(f, ".md"));
  const browser = await chromium.launch();
  try { for (const f of files) { await render(browser, path.resolve(f), outDir, names); } }
  finally { await browser.close(); }
})().catch((e) => { console.error(e.message || e); process.exit(1); });

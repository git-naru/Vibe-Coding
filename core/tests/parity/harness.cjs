#!/usr/bin/env node
/* Run the app's own page script (apps/pfd-flow-viewer/app.html) in Node so tests can compare pfdcore with it.
   The page is replaced by a stub that accepts any DOM call; pdf.js and SheetJS come from node_modules at the
   versions the app loads from the CDN. Reads one JSON request on stdin, writes one JSON answer on stdout:

     {"js": "<code run inside the page script's scope; its value is the answer>"}

   The code may use the app's own bindings (S, EQ, RATES, readPdf, computeCosts, …) and the helpers
   `fileEntry(path)` (a file entry like the app's upload list) and `workbook(path)` (SheetJS workbook). */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// stdout carries only the answer: pdf.js and the page script log through console.log
console.log = console.info = console.warn = (...a) => process.stderr.write(a.join(' ') + '\n');

const APP = path.resolve(__dirname, '../../../apps/pfd-flow-viewer/app.html');
const LAST = "renderSteps(); go('home'); initStore();";

function stub() {   // a callable that answers every property, call and assignment with itself
  const fn = function () {};
  const p = new Proxy(fn, {
    get: (t, k) => k === Symbol.toPrimitive ? () => '' : k === 'then' ? undefined : k === Symbol.iterator ? function* () {} : p,
    set: () => true, apply: () => p, construct: () => p, has: () => true, deleteProperty: () => true
  });
  return p;
}

function pageScript() {
  const html = fs.readFileSync(APP, 'utf8');
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  if (scripts.length !== 1) throw new Error(`expected one inline page script, found ${scripts.length}`);
  const js = scripts[0];
  if (!js.includes(LAST)) throw new Error('page script start-up line not found: ' + LAST);
  // stop before start-up; expose a direct eval so callers can reach the script-scope bindings
  return js.replace(LAST, `
needPdf = async () => {};
loadScript = async () => {};
globalThis.__inApp = src => eval(src);`);
}

function context() {
  const dom = stub();
  const ctx = {
    console, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    URL, Blob, TextDecoder, TextEncoder, AbortController, structuredClone, Intl, Buffer,
    document: dom, navigator: {}, location: dom, matchMedia: () => ({matches: false, addEventListener() {}}),
    pdfjsLib: require('pdfjs-dist/legacy/build/pdf.js'),
    XLSX: require('xlsx'),
    fileEntry: (p, id = 1) => {
      const buf = fs.readFileSync(p);
      return {id, kind: path.extname(p).slice(1).toLowerCase(), status: '대기', pages: null,
              file: {name: path.basename(p), size: buf.length, arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)}};
    },
    workbook: p => require('xlsx').read(fs.readFileSync(p), {type: 'buffer'})
  };
  ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
  ctx.pdfjsLib.GlobalWorkerOptions.workerSrc = require.resolve('pdfjs-dist/legacy/build/pdf.worker.js');
  ctx.withCMaps = () => {   // what the app would read if it gave pdf.js its CMap files
    const get = ctx.pdfjsLib.getDocument, dir = path.join(path.dirname(require.resolve('pdfjs-dist/package.json')), 'cmaps') + path.sep;
    ctx.pdfjsLib = {...ctx.pdfjsLib, getDocument: o => get({...o, cMapUrl: dir, cMapPacked: true})};
  };
  return vm.createContext(ctx);
}

// Sets and Maps made inside the page's context fail `instanceof` here, so check their tag
const tag = v => Object.prototype.toString.call(v);
const plain = (k, v) => tag(v) === '[object Set]' ? [...v] : tag(v) === '[object Map]' ? Object.fromEntries(v)
  : typeof v === 'number' && !Number.isFinite(v) ? {$num: String(v)} : v;

async function main() {
  const req = JSON.parse(fs.readFileSync(0, 'utf8'));
  const ctx = context();
  vm.runInContext(pageScript(), ctx, {filename: 'app.js'});
  const value = await ctx.__inApp(`(async () => { ${req.js} })()`);
  // exit once written: page timers (e.g. the debounced settings save) would otherwise keep Node alive
  process.stdout.write(JSON.stringify(value === undefined ? null : value, plain), () => process.exit(0));
}

main().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });

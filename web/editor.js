import {
  EditorState, EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter,
  defaultKeymap, history, historyKeymap, indentWithTab,
  searchKeymap, highlightSelectionMatches,
  closeBrackets, closeBracketsKeymap,
  StreamLanguage, syntaxHighlighting, HighlightStyle, tags, stex,
} from "./vendor/codemirror.bundle.js";
import * as pdfjsLib from "./vendor/pdfjs/pdf.mjs";
import { initSettings, getSettings } from "./settings.js";
import { grammarExtension, applyGrammarMatches, clearGrammarMatches } from "./grammar.js";
import { ghostExtension, showGhost, clearGhost } from "./ghosttext.js";
import { improveSelectionExtension, closeImproveButton } from "./improve.js";
import { showPrompt, showConfirm, showAlert, showImprovePreview } from "./dialogs.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/pdf.worker.mjs";

const huxleyHighlight = HighlightStyle.define([
  { tag: tags.comment, color: "#54627a", fontStyle: "italic" },
  { tag: tags.keyword, color: "#a3455a" },
  { tag: tags.tagName, color: "#a3455a" },
  { tag: [tags.string, tags.regexp], color: "#d4b483" },
  { tag: tags.bracket, color: "#6c7a92" },
  { tag: tags.attributeName, color: "#d4b483" },
]);

const darkTheme = EditorView.theme({
  "&": { backgroundColor: "#0e1420", color: "#c9d4e3", height: "100%" },
  ".cm-content": { caretColor: "#d4b483" },
  ".cm-selectionBackground": { backgroundColor: "#182337 !important" },
}, { dark: true });

const statusEl = document.getElementById("compile-status");
const filenameEl = document.getElementById("filename");
const logPanel = document.getElementById("log-panel");
const diagnosticsListEl = document.getElementById("diagnostics-list");
const rawLogEl = document.getElementById("raw-log");
const compileBtn = document.getElementById("compile-btn");
const pdfPane = document.getElementById("pdf-pane");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const openFolderBtn = document.getElementById("open-folder-btn");
const fileTreeEl = document.getElementById("file-tree");
const editorPane = document.getElementById("editor-pane");
const resizer = document.getElementById("resizer");
const logResizer = document.getElementById("log-resizer");

const PDF_SCALE = 1.4;

let view = null;
let currentPath = null;
let mainFilePath = null;
let pdfPages = []; // index i -> canvas for page i+1, populated by renderPdf()

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls;
}

function setDoc(content) {
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: content } });
}

function makeEditor(content) {
  const state = EditorState.create({
    doc: content,
    extensions: [
      lineNumbers(),
      history(),
      highlightActiveLine(),
      highlightActiveLineGutter(),
      closeBrackets(),
      highlightSelectionMatches(),
      StreamLanguage.define(stex),
      syntaxHighlighting(huxleyHighlight),
      darkTheme,
      keymap.of([...closeBracketsKeymap, ...defaultKeymap, ...historyKeymap, ...searchKeymap, indentWithTab]),
      EditorView.domEventHandlers({
        mousedown(event, cmView) {
          if (!event.ctrlKey) return false;
          const pos = cmView.posAtCoords({ x: event.clientX, y: event.clientY });
          if (pos == null) return false;
          forwardSearchAt(cmView.state.doc.lineAt(pos).number);
          return true;
        },
      }),
      grammarExtension,
      ghostExtension,
      improveSelectionExtension(handleImprove),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          scheduleGrammarCheck();
          scheduleGhostCheck(update.transactions.some((tr) => tr.isUserEvent("input.type")));
        } else if (update.selectionSet) {
          clearGhost(update.view);
        }
      }),
    ],
  });
  return new EditorView({ state, parent: document.getElementById("editor-pane") });
}

async function renderPdf() {
  // WebKitGTK's module-worker handshake is unreliable here, so render on the main thread.
  const doc = await pdfjsLib.getDocument({ url: "/api/pdf", disableWorker: true }).promise;
  pdfPane.innerHTML = "";
  pdfPages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const viewport = page.getViewport({ scale: PDF_SCALE });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.dataset.page = i;
    canvas.addEventListener("click", (event) => handlePdfClick(i, canvas, event));
    pdfPane.appendChild(canvas);
    pdfPages.push(canvas);
    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  }
}

async function handlePdfClick(pageNumber, canvas, event) {
  const rect = canvas.getBoundingClientRect();
  const x = ((event.clientX - rect.left) * (canvas.width / rect.width)) / PDF_SCALE;
  const y = ((event.clientY - rect.top) * (canvas.height / rect.height)) / PDF_SCALE;
  const res = await fetch("/api/synctex/inverse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page: pageNumber, x, y }),
  });
  if (!res.ok) return;
  const { path, line } = await res.json();
  await jumpToLine(path, line);
}

function flashPdfHighlight(canvas, x, y, width, height) {
  const box = document.createElement("div");
  box.className = "sync-highlight";
  box.style.left = `${canvas.offsetLeft + x * PDF_SCALE - 3}px`;
  box.style.top = `${canvas.offsetTop + y * PDF_SCALE - (height > 1 ? height : 14) * PDF_SCALE}px`;
  box.style.width = `${(width > 1 ? width : 150) * PDF_SCALE + 6}px`;
  box.style.height = `${(height > 1 ? height : 14) * PDF_SCALE + 4}px`;
  pdfPane.appendChild(box);
  requestAnimationFrame(() => box.classList.add("fade"));
  setTimeout(() => box.remove(), 1500);
}

async function forwardSearchAt(line) {
  if (!currentPath) return;
  const res = await fetch("/api/synctex/forward", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentPath, line }),
  });
  if (!res.ok) return;
  const { page, x, y, width, height } = await res.json();
  const canvas = pdfPages[page - 1];
  if (!canvas) return;
  const top = canvas.offsetTop + y * PDF_SCALE;
  const left = canvas.offsetLeft + x * PDF_SCALE;
  pdfPane.scrollTo({
    top: Math.max(0, top - pdfPane.clientHeight / 2),
    left: Math.max(0, left - pdfPane.clientWidth / 2),
    behavior: "smooth",
  });
  flashPdfHighlight(canvas, x, y, width, height);
}

async function openFile(path) {
  const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
  if (!res.ok) return;
  const { content } = await res.json();
  currentPath = path;
  filenameEl.textContent = path.split("/").pop();
  setDoc(content);
  for (const row of fileTreeEl.querySelectorAll(".tree-row.active")) row.classList.remove("active");
  const row = fileTreeEl.querySelector(`.tree-row[data-path="${CSS.escape(path)}"]`);
  if (row) row.classList.add("active");
}

let grammarDebounceTimer = null;

function scheduleGrammarCheck() {
  clearTimeout(grammarDebounceTimer);
  grammarDebounceTimer = setTimeout(runGrammarCheck, 800);
}

async function runGrammarCheck() {
  const settings = getSettings();
  if (!settings || !settings.grammar_enabled || currentPath === null) {
    clearGrammarMatches(view);
    return;
  }
  const text = view.state.doc.toString();
  const res = await fetch("/api/grammar/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) return;
  const { matches } = await res.json();
  // The doc may have changed again while we were waiting on the request.
  if (view.state.doc.toString() === text) applyGrammarMatches(view, text, matches);
}

let ghostDebounceTimer = null;

function scheduleGhostCheck(isUserTyping) {
  clearGhost(view);
  clearTimeout(ghostDebounceTimer);
  if (!isUserTyping) return;
  const settings = getSettings();
  if (!settings || !settings.autocomplete_enabled) return;
  if (!view.state.selection.main.empty) return;
  const pos = view.state.selection.main.head;
  ghostDebounceTimer = setTimeout(() => runGhostCheck(pos), 500);
}

async function runGhostCheck(pos) {
  if (view.state.selection.main.head !== pos) return;
  const docText = view.state.doc.toString();
  const res = await fetch("/api/ai/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prefix: docText.slice(0, pos), suffix: docText.slice(pos) }),
  });
  if (!res.ok) return;
  const { completion } = await res.json();
  if (!completion || view.state.selection.main.head !== pos) return;
  showGhost(view, pos, completion);
}

async function jumpToLine(file, line) {
  if (file && file !== currentPath) {
    await openFile(file);
  }
  if (line) {
    const lineNumber = Math.max(1, Math.min(line, view.state.doc.lines));
    const pos = view.state.doc.line(lineNumber).from;
    view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
  }
  view.focus();
}

function renderDiagnostics(diagnostics, rawLog) {
  diagnosticsListEl.innerHTML = "";

  const hasContent = diagnostics.length > 0 || (rawLog && rawLog.trim());
  logPanel.classList.toggle("visible", Boolean(hasContent));
  logResizer.classList.toggle("visible", Boolean(hasContent));
  if (!hasContent) {
    rawLogEl.value = "";
    return;
  }

  logPanel.classList.toggle("error", diagnostics.some((d) => d.severity === "error"));
  rawLogEl.value = rawLog || "";

  for (const diagnostic of diagnostics) {
    const row = document.createElement("div");
    row.className = `diag-row ${diagnostic.severity}`;

    const severity = document.createElement("span");
    severity.className = "diag-severity";
    severity.textContent = diagnostic.severity === "error" ? "✕" : "⚠";
    row.appendChild(severity);

    if (diagnostic.file) {
      const location = document.createElement("span");
      location.className = "diag-location";
      const name = diagnostic.file.split("/").pop();
      location.textContent = diagnostic.line ? `${name}:${diagnostic.line}` : name;
      row.appendChild(location);
    }

    const message = document.createElement("span");
    message.className = "diag-message";
    message.textContent = diagnostic.message;
    row.appendChild(message);

    const explainBtn = document.createElement("button");
    explainBtn.className = "diag-explain-btn";
    explainBtn.type = "button";
    explainBtn.textContent = "✨ Explain";
    explainBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      explainDiagnostic(diagnostic, rawLog, explainBtn, row);
    });
    row.appendChild(explainBtn);

    row.addEventListener("click", () => jumpToLine(diagnostic.file, diagnostic.line));
    diagnosticsListEl.appendChild(row);
  }
}

async function explainDiagnostic(diagnostic, rawLog, button, row) {
  const existing = row.nextElementSibling;
  if (existing && existing.classList.contains("diag-explanation")) {
    existing.remove();
    return;
  }
  button.disabled = true;
  button.textContent = "Explaining…";
  const box = document.createElement("div");
  box.className = "diag-explanation";
  try {
    const res = await fetch("/api/ai/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: diagnostic.message, log: rawLog || "" }),
    });
    const data = await res.json();
    box.textContent = res.ok ? data.explanation : data.detail || "Could not get an explanation.";
  } catch {
    box.textContent = "Could not reach the AI endpoint. Check Settings.";
  }
  row.insertAdjacentElement("afterend", box);
  button.disabled = false;
  button.textContent = "✨ Explain";
}

async function handleImprove(text, from, to) {
  let improved;
  try {
    const res = await fetch("/api/ai/improve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    closeImproveButton();
    if (!res.ok) {
      await showAlert(data.detail || "Could not improve the selection.");
      return;
    }
    improved = data.improved;
  } catch {
    closeImproveButton();
    await showAlert("Could not reach the AI endpoint. Check Settings.");
    return;
  }
  const result = await showImprovePreview(text, improved);
  if (result !== null) {
    view.dispatch({ changes: { from, to, insert: result } });
  }
}

async function compile() {
  if (currentPath === null) return;
  await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentPath, content: view.state.doc.toString() }),
  });
  await fetch("/api/compile", { method: "POST" });
}

function connectStatusSocket() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.status === "compiling") {
      compileBtn.disabled = true;
      setStatus("compiling…", "running");
      renderDiagnostics([], "");
    } else if (msg.status === "ok") {
      compileBtn.disabled = false;
      setStatus("ok", "ok");
      renderDiagnostics(msg.diagnostics || [], msg.log);
      renderPdf();
    } else if (msg.status === "error") {
      compileBtn.disabled = false;
      setStatus("error", "error");
      renderDiagnostics(msg.diagnostics || [], msg.log);
    }
  });
  ws.addEventListener("close", () => setTimeout(connectStatusSocket, 1000));
}

const expandedDirs = new Set();

async function refreshTree() {
  await renderTreeInto(fileTreeEl, "");
}

// True if `path` is entry.path itself, or lives inside it (entry.path is a
// directory ancestor) — used to remap/clear open files affected by a rename
// or delete of a containing folder, not just an exact path match.
function isWithin(path, entryPath) {
  return path === entryPath || (path && path.startsWith(`${entryPath}/`));
}

async function renameEntry(entry) {
  const oldName = entry.path.split("/").pop();
  const newName = await showPrompt(entry.type === "dir" ? "Rename folder:" : "Rename file:", oldName);
  if (!newName || newName === oldName) return;
  const res = await fetch("/api/file/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: entry.path, new_name: newName }),
  });
  const data = await res.json();
  if (!res.ok) {
    await showAlert(data.detail || "Rename failed.");
    return;
  }
  if (isWithin(currentPath, entry.path)) {
    currentPath = data.path + currentPath.slice(entry.path.length);
    filenameEl.textContent = currentPath.split("/").pop();
  }
  if (isWithin(mainFilePath, entry.path)) {
    mainFilePath = data.path + mainFilePath.slice(entry.path.length);
  }
  await refreshTree();
}

async function deleteEntry(entry) {
  const message = entry.type === "dir"
    ? `Delete folder "${entry.name}" and everything in it? This cannot be undone.`
    : `Delete "${entry.name}"? This cannot be undone.`;
  const confirmed = await showConfirm(message, { danger: true, confirmLabel: "Delete" });
  if (!confirmed) return;
  const res = await fetch("/api/file/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: entry.path }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    await showAlert(data.detail || "Delete failed.");
    return;
  }
  if (isWithin(currentPath, entry.path)) {
    currentPath = null;
    filenameEl.textContent = "";
    setDoc("");
  }
  const status = await fetch("/api/status").then((r) => r.json());
  mainFilePath = status.main_file;
  await refreshTree();
}

async function createFileIn(dirPath) {
  const name = await showPrompt(dirPath ? `New file in ${dirPath}/:` : "New file:", "untitled.tex");
  if (!name) return;
  const fullPath = dirPath ? `${dirPath}/${name}` : name;
  const res = await fetch("/api/file/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: fullPath }),
  });
  const data = await res.json();
  if (!res.ok) {
    await showAlert(data.detail || "Could not create file.");
    return;
  }
  if (dirPath) expandedDirs.add(dirPath);
  await refreshTree();
  await openFile(fullPath);
}

let activeContextMenu = null;
let activeContextMenuOutsideHandler = null;

function closeContextMenu() {
  if (activeContextMenuOutsideHandler) {
    window.removeEventListener("mousedown", activeContextMenuOutsideHandler);
    activeContextMenuOutsideHandler = null;
  }
  if (activeContextMenu) {
    activeContextMenu.remove();
    activeContextMenu = null;
  }
}

function showContextMenu(x, y, items) {
  closeContextMenu();
  const menu = document.createElement("div");
  menu.className = "context-menu";
  for (const item of items) {
    const entry = document.createElement("div");
    entry.className = "context-menu-item" + (item.danger ? " danger" : "");
    entry.textContent = item.label;
    // click fires after mousedown+mouseup on the same element — using it here
    // (rather than mousedown) means the outside-click handler below, which
    // only closes on mousedown *outside* the menu, never races this.
    entry.addEventListener("click", () => {
      closeContextMenu();
      item.action();
    });
    menu.appendChild(entry);
  }
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  document.body.appendChild(menu);
  activeContextMenu = menu;

  activeContextMenuOutsideHandler = (event) => {
    if (!menu.contains(event.target)) closeContextMenu();
  };
  setTimeout(() => window.addEventListener("mousedown", activeContextMenuOutsideHandler), 0);
}

async function renderTreeInto(container, dirPath) {
  const res = await fetch(`/api/tree?path=${encodeURIComponent(dirPath)}`);
  const entries = await res.json();
  container.innerHTML = "";
  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "tree-row";
    row.dataset.path = entry.path;

    const caret = document.createElement("span");
    caret.className = "caret";
    caret.textContent = entry.type === "dir" ? "▸" : "";
    row.appendChild(caret);

    const isMain = entry.type === "file" && entry.path === mainFilePath;
    const icon = document.createElement("span");
    icon.className = "icon";
    icon.textContent = entry.type === "dir" ? "" : isMain ? "★" : "▪";
    if (isMain) icon.title = "Compile target";
    row.appendChild(icon);

    const label = document.createElement("span");
    label.textContent = entry.name;
    row.appendChild(label);

    container.appendChild(row);

    if (entry.type === "dir") {
      const children = document.createElement("div");
      children.className = "tree-children";
      children.style.paddingLeft = "12px";
      container.appendChild(children);

      let loaded = false;
      const isExpanded = expandedDirs.has(entry.path);
      if (isExpanded) {
        children.classList.add("expanded");
        caret.classList.add("expanded");
        loaded = true;
      }

      row.addEventListener("click", async () => {
        const expanded = children.classList.toggle("expanded");
        caret.classList.toggle("expanded", expanded);
        if (expanded) {
          expandedDirs.add(entry.path);
          if (!loaded) {
            loaded = true;
            await renderTreeInto(children, entry.path);
          }
        } else {
          expandedDirs.delete(entry.path);
        }
      });
      row.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        showContextMenu(event.clientX, event.clientY, [
          { label: "New File", action: () => createFileIn(entry.path) },
          { label: "Rename", action: () => renameEntry(entry) },
          { label: "Delete", danger: true, action: () => deleteEntry(entry) },
        ]);
      });

      if (isExpanded) await renderTreeInto(children, entry.path);
    } else {
      row.addEventListener("click", () => openFile(entry.path));
      row.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        showContextMenu(event.clientX, event.clientY, [
          { label: "Rename", action: () => renameEntry(entry) },
          { label: "Delete", danger: true, action: () => deleteEntry(entry) },
        ]);
      });
    }
  }
}

async function openFolderDialog() {
  if (!window.pywebview) return;
  const path = await window.pywebview.api.open_folder();
  if (!path) return;
  await fetch("/api/open-folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  await init();
}

async function init() {
  const status = await fetch("/api/status").then((r) => r.json());
  mainFilePath = status.main_file;
  expandedDirs.clear();
  await renderTreeInto(fileTreeEl, "");

  pdfPane.innerHTML = '<div id="pdf-empty">Compile to see your PDF here.</div>';
  renderDiagnostics([], "");
  setStatus("idle", "idle");

  if (status.main_file) {
    await openFile(status.main_file);
  } else {
    currentPath = null;
    filenameEl.textContent = "";
    setDoc("");
  }
}

function initResizer() {
  const MIN_PANE = 200;
  let dragging = false;

  resizer.addEventListener("mousedown", (event) => {
    dragging = true;
    resizer.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    event.preventDefault();
  });

  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    const mainRect = document.getElementById("main").getBoundingClientRect();
    const editorLeft = editorPane.getBoundingClientRect().left;
    const maxWidth = mainRect.right - editorLeft - MIN_PANE - resizer.getBoundingClientRect().width;
    const width = Math.max(MIN_PANE, Math.min(event.clientX - editorLeft, maxWidth));
    editorPane.style.flex = `0 0 ${width}px`;
    view.requestMeasure();
  });

  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove("dragging");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
}

function initLogResizer() {
  const MIN_HEIGHT = 60;
  let dragging = false;

  logResizer.addEventListener("mousedown", (event) => {
    dragging = true;
    logResizer.classList.add("dragging");
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    event.preventDefault();
  });

  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    const appRect = document.getElementById("app").getBoundingClientRect();
    const maxHeight = appRect.height - 150; // leave room for the topbar and a usable editor/pdf area
    const height = Math.max(MIN_HEIGHT, Math.min(appRect.bottom - event.clientY, maxHeight));
    logPanel.style.height = `${height}px`;
    view.requestMeasure();
  });

  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    logResizer.classList.remove("dragging");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
}

(async () => {
  view = makeEditor("");
  compileBtn.addEventListener("click", compile);
  sidebarToggle.addEventListener("click", () => sidebar.classList.toggle("collapsed"));
  openFolderBtn.addEventListener("click", openFolderDialog);
  fileTreeEl.addEventListener("contextmenu", (event) => {
    if (event.target !== fileTreeEl) return;
    event.preventDefault();
    showContextMenu(event.clientX, event.clientY, [{ label: "New File", action: () => createFileIn("") }]);
  });
  initResizer();
  initLogResizer();
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      compile();
    }
  });
  connectStatusSocket();
  await initSettings();
  await init();
})();

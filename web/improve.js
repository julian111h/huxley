import { EditorView } from "./vendor/codemirror.bundle.js";

let btnEl = null;

export function closeImproveButton() {
  if (btnEl) {
    btnEl.remove();
    btnEl = null;
  }
}

function showImproveButton(view, onClick) {
  closeImproveButton();
  const sel = view.state.selection.main;
  const coords = view.coordsAtPos(sel.head);
  if (!coords) return;

  const btn = document.createElement("button");
  btn.className = "improve-btn";
  btn.type = "button";
  btn.textContent = "✨ Improve";
  btn.style.left = `${coords.left}px`;
  btn.style.top = `${coords.bottom + 6}px`;
  // Selecting text with a mouse drag ends in a mouseup; a mousedown on this
  // button would otherwise fire first and collapse the selection before click.
  btn.addEventListener("mousedown", (event) => event.preventDefault());
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Improving…";
    await onClick(view.state.sliceDoc(sel.from, sel.to), sel.from, sel.to);
  });
  document.body.appendChild(btn);
  btnEl = btn;
}

export function improveSelectionExtension(onImprove) {
  return EditorView.updateListener.of((update) => {
    if (!update.selectionSet && !update.docChanged) return;
    const sel = update.state.selection.main;
    if (sel.empty) {
      closeImproveButton();
    } else {
      showImproveButton(update.view, onImprove);
    }
  });
}

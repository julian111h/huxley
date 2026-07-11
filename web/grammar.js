import { StateField, StateEffect, Decoration, EditorView } from "./vendor/codemirror.bundle.js";

const setMatches = StateEffect.define();

export const grammarField = StateField.define({
  create() {
    return Decoration.none;
  },
  update(decorations, tr) {
    decorations = decorations.map(tr.changes);
    for (const effect of tr.effects) {
      if (effect.is(setMatches)) decorations = effect.value;
    }
    return decorations;
  },
  provide: (field) => EditorView.decorations.from(field),
});

let popupEl = null;

function closePopup() {
  if (popupEl) {
    popupEl.remove();
    popupEl = null;
  }
}

function showPopup(view, match, coords) {
  closePopup();
  popupEl = document.createElement("div");
  popupEl.className = "grammar-popup";

  const msg = document.createElement("div");
  msg.className = "grammar-popup-message";
  msg.textContent = match.message;
  popupEl.appendChild(msg);

  const actions = document.createElement("div");
  actions.className = "grammar-popup-actions";
  for (const replacement of match.replacements) {
    const btn = document.createElement("button");
    btn.textContent = replacement || "(remove)";
    btn.addEventListener("click", () => {
      view.dispatch({ changes: { from: match.from, to: match.to, insert: replacement } });
      closePopup();
    });
    actions.appendChild(btn);
  }
  popupEl.appendChild(actions);

  popupEl.style.left = `${coords.left}px`;
  popupEl.style.top = `${coords.bottom + 4}px`;
  document.body.appendChild(popupEl);
}

const grammarClickHandler = EditorView.domEventHandlers({
  mousedown(event, view) {
    closePopup();
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
    if (pos == null) return false;
    let found = null;
    view.state.field(grammarField).between(pos, pos, (from, to, deco) => {
      found = { from, to, ...deco.spec.match };
    });
    if (!found) return false;
    const coords = view.coordsAtPos(pos) || { left: event.clientX, bottom: event.clientY };
    showPopup(view, found, coords);
    return false;
  },
});

export const grammarExtension = [grammarField, grammarClickHandler];

export function applyGrammarMatches(view, text, matches) {
  const ranges = matches
    .filter((m) => m.length > 0 && m.offset + m.length <= text.length)
    .map((m) =>
      Decoration.mark({
        class: "grammar-issue",
        match: { message: m.message, replacements: m.replacements.length ? m.replacements : [""] },
      }).range(m.offset, m.offset + m.length)
    );
  ranges.sort((a, b) => a.from - b.from);
  view.dispatch({ effects: setMatches.of(Decoration.set(ranges, true)) });
}

export function clearGrammarMatches(view) {
  view.dispatch({ effects: setMatches.of(Decoration.none) });
}

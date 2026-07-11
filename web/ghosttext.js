import { StateField, StateEffect, Decoration, WidgetType, EditorView, keymap, Prec } from "./vendor/codemirror.bundle.js";

class GhostWidget extends WidgetType {
  constructor(text) {
    super();
    this.text = text;
  }
  eq(other) {
    return other.text === this.text;
  }
  toDOM() {
    const span = document.createElement("span");
    span.className = "ghost-text";
    span.textContent = this.text;
    return span;
  }
}

const setGhost = StateEffect.define();
const EMPTY = { pos: -1, text: "", deco: Decoration.none };

export const ghostField = StateField.define({
  create() {
    return EMPTY;
  },
  update(value, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setGhost)) {
        const { pos, text } = effect.value;
        if (!text) return EMPTY;
        return {
          pos,
          text,
          deco: Decoration.set([Decoration.widget({ widget: new GhostWidget(text), side: 1 }).range(pos)]),
        };
      }
    }
    if (tr.docChanged || tr.selection) return EMPTY;
    return value;
  },
  provide: (field) => EditorView.decorations.from(field, (v) => v.deco),
});

export function showGhost(view, pos, text) {
  if (view.state.selection.main.head !== pos) return;
  view.dispatch({ effects: setGhost.of({ pos, text }) });
}

export function clearGhost(view) {
  if (view.state.field(ghostField).text) view.dispatch({ effects: setGhost.of({ pos: -1, text: "" }) });
}

function acceptGhost(view) {
  const { pos, text } = view.state.field(ghostField);
  if (!text) return false;
  view.dispatch({
    changes: { from: pos, to: pos, insert: text },
    selection: { anchor: pos + text.length },
    effects: setGhost.of({ pos: -1, text: "" }),
  });
  return true;
}

export const ghostExtension = [
  ghostField,
  Prec.highest(
    keymap.of([
      { key: "Tab", run: acceptGhost },
      {
        key: "Escape",
        run: (view) => {
          if (!view.state.field(ghostField).text) return false;
          clearGhost(view);
          return true;
        },
      },
    ])
  ),
];

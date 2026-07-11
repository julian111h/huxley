function createOverlay(contentEl, { wide = false } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "dialog-overlay visible";
  const modal = document.createElement("div");
  modal.className = wide ? "dialog-modal wide" : "dialog-modal";
  modal.appendChild(contentEl);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  return overlay;
}

function buildActions(buttons) {
  const actions = document.createElement("div");
  actions.className = "dialog-actions";
  for (const btn of buttons) actions.appendChild(btn);
  return actions;
}

export function showAlert(message) {
  return new Promise((resolve) => {
    const content = document.createElement("div");
    content.className = "dialog-body";
    const msg = document.createElement("p");
    msg.textContent = message;
    content.appendChild(msg);

    const okBtn = document.createElement("button");
    okBtn.textContent = "OK";
    okBtn.className = "dialog-btn-primary";
    content.appendChild(buildActions([okBtn]));

    const overlay = createOverlay(content);
    const close = () => {
      overlay.remove();
      resolve();
    };
    okBtn.addEventListener("click", close);
    overlay.addEventListener("click", (e) => e.target === overlay && close());
    okBtn.focus();
  });
}

export function showConfirm(message, { danger = false, confirmLabel = "OK" } = {}) {
  return new Promise((resolve) => {
    const content = document.createElement("div");
    content.className = "dialog-body";
    const msg = document.createElement("p");
    msg.textContent = message;
    content.appendChild(msg);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.className = "dialog-btn-secondary";
    const okBtn = document.createElement("button");
    okBtn.textContent = confirmLabel;
    okBtn.className = danger ? "dialog-btn-danger" : "dialog-btn-primary";
    content.appendChild(buildActions([cancelBtn, okBtn]));

    const overlay = createOverlay(content);
    const close = (result) => {
      overlay.remove();
      resolve(result);
    };
    cancelBtn.addEventListener("click", () => close(false));
    okBtn.addEventListener("click", () => close(true));
    overlay.addEventListener("click", (e) => e.target === overlay && close(false));
    okBtn.focus();
  });
}

export function showPrompt(message, defaultValue = "") {
  return new Promise((resolve) => {
    const content = document.createElement("div");
    content.className = "dialog-body";
    const msg = document.createElement("p");
    msg.textContent = message;
    content.appendChild(msg);

    const input = document.createElement("input");
    input.type = "text";
    input.className = "dialog-input";
    input.value = defaultValue;
    content.appendChild(input);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.className = "dialog-btn-secondary";
    const okBtn = document.createElement("button");
    okBtn.textContent = "OK";
    okBtn.className = "dialog-btn-primary";
    content.appendChild(buildActions([cancelBtn, okBtn]));

    const overlay = createOverlay(content);
    const close = (result) => {
      overlay.remove();
      resolve(result);
    };
    cancelBtn.addEventListener("click", () => close(null));
    okBtn.addEventListener("click", () => close(input.value.trim() || null));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") close(input.value.trim() || null);
      if (e.key === "Escape") close(null);
    });
    overlay.addEventListener("click", (e) => e.target === overlay && close(null));
    requestAnimationFrame(() => {
      input.focus();
      const dot = input.value.lastIndexOf(".");
      input.setSelectionRange(0, dot > 0 ? dot : input.value.length);
    });
  });
}

export function showImprovePreview(original, improved) {
  return new Promise((resolve) => {
    const content = document.createElement("div");
    content.className = "dialog-body improve-dialog";

    const origLabel = document.createElement("div");
    origLabel.className = "improve-label";
    origLabel.textContent = "Original";
    content.appendChild(origLabel);
    const origBox = document.createElement("div");
    origBox.className = "improve-text improve-original";
    origBox.textContent = original;
    content.appendChild(origBox);

    const newLabel = document.createElement("div");
    newLabel.className = "improve-label";
    newLabel.textContent = "Improved (editable)";
    content.appendChild(newLabel);
    const newBox = document.createElement("textarea");
    newBox.className = "improve-text improve-editable";
    newBox.value = improved;
    content.appendChild(newBox);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Discard";
    cancelBtn.className = "dialog-btn-secondary";
    const applyBtn = document.createElement("button");
    applyBtn.textContent = "Apply";
    applyBtn.className = "dialog-btn-primary";
    content.appendChild(buildActions([cancelBtn, applyBtn]));

    const overlay = createOverlay(content, { wide: true });
    const close = (result) => {
      overlay.remove();
      resolve(result);
    };
    cancelBtn.addEventListener("click", () => close(null));
    applyBtn.addEventListener("click", () => close(newBox.value));
    overlay.addEventListener("click", (e) => e.target === overlay && close(null));
  });
}

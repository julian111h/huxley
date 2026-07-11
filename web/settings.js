import { createCombobox } from "./combobox.js";

let currentSettings = null;

export function getSettings() {
  return currentSettings;
}

function setModelOptions(combo, models, selected) {
  combo.setOptions([{ value: "", label: "(none selected)" }, ...models.map((m) => ({ value: m, label: m }))]);
  combo.value = selected || "";
}

export async function initSettings() {
  currentSettings = await fetch("/api/settings").then((r) => r.json());

  const overlay = document.getElementById("settings-overlay");
  const openBtn = document.getElementById("settings-btn");
  const closeBtn = document.getElementById("settings-close");
  const saveBtn = document.getElementById("settings-save");
  const refreshBtn = document.getElementById("settings-refresh-models");
  const baseUrlInput = document.getElementById("setting-base-url");
  const chatCombo = createCombobox(document.getElementById("setting-chat-model"));
  const autocompleteCombo = createCombobox(document.getElementById("setting-autocomplete-model"));
  const autocompleteEnabled = document.getElementById("setting-autocomplete-enabled");
  const grammarEnabled = document.getElementById("setting-grammar-enabled");
  const statusEl = document.getElementById("settings-status");

  async function refreshModels() {
    statusEl.textContent = "Loading models…";
    const baseUrl = baseUrlInput.value.trim();
    if (baseUrl && baseUrl !== currentSettings.ai_base_url) {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ai_base_url: baseUrl }),
      });
      currentSettings.ai_base_url = baseUrl;
    }
    try {
      const res = await fetch("/api/ai/models");
      if (!res.ok) throw new Error();
      const { models } = await res.json();
      setModelOptions(chatCombo, models, currentSettings.chat_model);
      setModelOptions(autocompleteCombo, models, currentSettings.autocomplete_model);
      statusEl.textContent = models.length ? `Found ${models.length} model(s).` : "No models found.";
    } catch {
      statusEl.textContent = "Could not reach the AI endpoint — check the base URL.";
    }
  }

  function openModal() {
    baseUrlInput.value = currentSettings.ai_base_url;
    autocompleteEnabled.checked = currentSettings.autocomplete_enabled;
    grammarEnabled.checked = currentSettings.grammar_enabled;
    statusEl.textContent = "";
    overlay.classList.add("visible");
    refreshModels();
  }

  openBtn.addEventListener("click", openModal);
  closeBtn.addEventListener("click", () => overlay.classList.remove("visible"));
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) overlay.classList.remove("visible");
  });
  refreshBtn.addEventListener("click", refreshModels);

  saveBtn.addEventListener("click", async () => {
    const updates = {
      ai_base_url: baseUrlInput.value.trim(),
      chat_model: chatCombo.value,
      autocomplete_model: autocompleteCombo.value,
      autocomplete_enabled: autocompleteEnabled.checked,
      grammar_enabled: grammarEnabled.checked,
    };
    currentSettings = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }).then((r) => r.json());
    overlay.classList.remove("visible");
  });
}

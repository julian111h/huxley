// A minimal dropdown replacement for <select>: WebKitGTK renders the native
// <select> popup with its own GTK theme, ignoring page CSS entirely, which
// left it unreadable against this app's dark theme. This one is plain DOM,
// fully themeable, and exposes just enough of the <select> surface
// (`.value` get/set, `change` events) to drop in anywhere a select was used.
export function createCombobox(container) {
  container.classList.add("combo");
  container.innerHTML = "";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "combo-trigger";
  trigger.textContent = "(none selected)";

  const list = document.createElement("div");
  list.className = "combo-list";

  container.appendChild(trigger);
  container.appendChild(list);

  let options = [];
  let value = "";

  function onOutsideClick(event) {
    if (!container.contains(event.target)) close();
  }

  function open() {
    list.classList.add("open");
    setTimeout(() => document.addEventListener("mousedown", onOutsideClick), 0);
  }

  function close() {
    list.classList.remove("open");
    document.removeEventListener("mousedown", onOutsideClick);
  }

  trigger.addEventListener("click", () => {
    if (list.classList.contains("open")) close();
    else open();
  });

  function labelFor(v) {
    return options.find((o) => o.value === v)?.label ?? "(none selected)";
  }

  function render() {
    list.innerHTML = "";
    for (const opt of options) {
      const item = document.createElement("div");
      item.className = "combo-item" + (opt.value === value ? " selected" : "");
      item.textContent = opt.label;
      item.addEventListener("click", () => {
        value = opt.value;
        trigger.textContent = labelFor(value);
        close();
        container.dispatchEvent(new Event("change"));
      });
      list.appendChild(item);
    }
  }

  return {
    setOptions(opts) {
      options = opts;
      trigger.textContent = labelFor(value);
      render();
    },
    get value() {
      return value;
    },
    set value(v) {
      value = v;
      trigger.textContent = labelFor(value);
      render();
    },
    addEventListener: (type, fn) => container.addEventListener(type, fn),
  };
}

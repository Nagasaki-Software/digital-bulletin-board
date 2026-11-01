const overlay = document.getElementById("picker");

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function btn(text, cls, onClick) {
  const b = el("button", cls, text);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

function open(build) {
  return new Promise(resolve => {
    overlay.innerHTML = "";
    const panel = el("div", "panel");
    overlay.appendChild(panel);
    const close = value => {
      overlay.hidden = true;
      overlay.innerHTML = "";
      resolve(value);
    };
    build(panel, close);
    overlay.hidden = false;
  });
}

export function pickOption({ title, options, current = "", allowClear = true }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const grid = el("div", "options");
    for (const o of options) {
      const value = typeof o === "string" ? o : o.value;
      const label = typeof o === "string" ? o : o.label;
      grid.appendChild(btn(label, "opt" + (value === current ? " current" : ""), () => close(value)));
    }
    panel.appendChild(grid);
    const actions = el("div", "panel-actions");
    if (allowClear) actions.appendChild(btn("クリア", "opt", () => close("")));
    actions.appendChild(btn("閉じる", "opt", () => close(undefined)));
    panel.appendChild(actions);
  });
}

export function inputText({ title, value = "", flagLabel = "", flag = false }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const input = el("input");
    input.type = "text";
    input.value = value;
    panel.appendChild(input);
    let check = null;
    if (flagLabel) {
      const label = el("label", "radio");
      check = el("input");
      check.type = "checkbox";
      check.checked = flag;
      label.append(check, document.createTextNode(" " + flagLabel));
      panel.appendChild(label);
    }
    const submit = () => close({ text: input.value.trim(), flag: check ? check.checked : false });
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("キャンセル", "opt", () => close(undefined)));
    actions.appendChild(btn("決定", "opt current", submit));
    panel.appendChild(actions);
    input.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.isComposing) submit();
    });
    setTimeout(() => input.focus(), 0);
  });
}

export function confirmBox(message, okLabel = "はい") {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", message));
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("やめる", "opt", () => close(false)));
    actions.appendChild(btn(okLabel, "opt current", () => close(true)));
    panel.appendChild(actions);
  });
}

export function alertBox(message) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", message));
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("閉じる", "opt current", () => close()));
    panel.appendChild(actions);
  });
}

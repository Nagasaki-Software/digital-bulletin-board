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

const TYPE_IT = Symbol("type");
export const FREE_TEXT_MAX = 30; // サーバー（app.py の FREE_TEXT_MAX）と同じ

// allowText: 選択肢の最後に「その他（手入力）」を出し、押したらキーボードで入力する窓を開く
export async function pickOption({ title, options, current = "", allowClear = true, allowText = false }) {
  const values = options.map(o => (typeof o === "string" ? o : o.value));
  const v = await open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const grid = el("div", "options");
    for (const o of options) {
      const value = typeof o === "string" ? o : o.value;
      const label = typeof o === "string" ? o : o.label;
      grid.appendChild(btn(label, "opt" + (value === current ? " current" : ""), () => close(value)));
    }
    if (allowText) {
      const typed = current && !values.includes(current);
      grid.appendChild(btn(typed ? `その他（手入力）: ${current}` : "その他（手入力）", "opt type-it" + (typed ? " current" : ""), () => close(TYPE_IT)));
    }
    panel.appendChild(grid);
    const actions = el("div", "panel-actions");
    if (allowClear) actions.appendChild(btn("クリア", "opt", () => close("")));
    actions.appendChild(btn("閉じる", "opt", () => close(undefined)));
    panel.appendChild(actions);
  });
  if (v !== TYPE_IT) return v;
  const r = await inputText({ title: title + "（手入力）", value: current, maxLength: FREE_TEXT_MAX });
  return r === undefined ? undefined : r.text;
}

export function inputText({ title, value = "", flagLabel = "", flag = false, maxLength = 0 }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const input = el("input");
    input.type = "text";
    input.value = value;
    if (maxLength) input.maxLength = maxLength;
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

// 数字だけを押して入れる窓（タッチ用のテンキー）。決定なら数字の文字列（空もある）、キャンセルなら undefined
export function inputNumber({ title, value = "", maxDigits = 3, unit = "" }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    let text = String(value);
    const shown = el("div", "num-shown");
    const show = () => { shown.textContent = text === "" ? "（空）" : text + unit; };
    show();
    panel.appendChild(shown);
    const pad = el("div", "num-pad");
    for (const k of ["7", "8", "9", "4", "5", "6", "1", "2", "3", "クリア", "0", "←"]) {
      pad.appendChild(btn(k, "opt", () => {
        if (k === "クリア") text = "";
        else if (k === "←") text = text.slice(0, -1);
        else if (text.length < maxDigits) text = text === "0" ? k : text + k;
        show();
      }));
    }
    panel.appendChild(pad);
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("キャンセル", "opt", () => close(undefined)));
    actions.appendChild(btn("決定", "opt current", () => close(text)));
    panel.appendChild(actions);
  });
}

// 開始日と終了日（"2026-11-03" の形）を選ぶ。キャンセルなら undefined
export function inputPeriod({ title, start, end }) {
  return open((panel, close) => {
    panel.appendChild(el("h3", "", title));
    const inputs = [["開始日", start], ["終了日", end]].map(([label, value]) => {
      const line = el("label", "field-line");
      const input = el("input");
      input.type = "date";
      input.value = value;
      line.append(el("span", "", label), input);
      panel.appendChild(line);
      return input;
    });
    const actions = el("div", "panel-actions");
    actions.appendChild(btn("キャンセル", "opt", () => close(undefined)));
    actions.appendChild(btn("決定", "opt current", () => close({ start: inputs[0].value, end: inputs[1].value })));
    panel.appendChild(actions);
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

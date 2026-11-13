// 押した値を、サーバーの返事を待たずに画面の内容（state）へ先に入れる。
// 回線が遅くても押した手応えがすぐ返るようにするため。保存のあとで取り直すので、違っていてもすぐ正しい内容に戻る。
// サーバー側（app.py）の決まりと同じにする：所属を変えたら責任者（使用者）を空、工事件名で選べない作業内容は空。
// 先に書き換えたら true、書き換えられないもの（追加・削除・並べ替え・行が無い）は何もせず false。

const TABLES = { schedule: "schedule", "holiday-rows": "holiday_rows", equipment: "equipment", notices: "notices" };

function setContact(state, row, companyKey) {
  const l = (state.masters.leaders || []).find(x => x.company === row[companyKey] && x.leader_name === row.leader);
  row.ext = l ? l.ext : "";
  row.outside = l ? l.outside : "";
}

export function applyLocal(state, method, url, body) {
  if (!state || !body) return false;
  if (method === "POST" && url === "/api/genres/toggle") {
    const list = state.checked_genres.filter(g => g !== body.name);
    if (body.checked) list.push(body.name);
    state.checked_genres = list;
    return true;
  }
  const m = /^\/api\/([a-z-]+)\/(\d+)$/.exec(url);
  if (method !== "PATCH" || !m || !TABLES[m[1]]) return false;
  const row = (state[TABLES[m[1]]] || []).find(r => r.id === Number(m[2]));
  if (!row) return false;
  const kind = m[1];
  const companyKey = kind === "holiday-rows" ? "person" : "company";
  const personKey = kind === "equipment" ? "user" : "leader";
  const before = { ...row };
  Object.assign(row, body);
  if (kind !== "notices" && companyKey in body && body[companyKey] !== before[companyKey] && !(personKey in body)) row[personKey] = "";
  if ((kind === "schedule" || kind === "holiday-rows") && (row.leader !== before.leader || row[companyKey] !== before[companyKey])) setContact(state, row, companyKey);
  if ("construction" in body && body.construction !== before.construction && !("work" in body)) {
    const allowed = (state.masters.construction_works || {})[row.construction];
    if (allowed && allowed.length && !allowed.includes(row.work)) row.work = "";
  }
  return true;
}

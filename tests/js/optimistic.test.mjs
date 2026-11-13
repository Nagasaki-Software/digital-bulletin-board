import test from "node:test";
import assert from "node:assert/strict";
import { applyLocal } from "../../static/js/optimistic.mjs";

function sample() {
  return {
    masters: {
      leaders: [
        { company: "1班", leader_name: "佐藤", ext: "1234", outside: "" },
        { company: "見本電機", leader_name: "田中", ext: "", outside: "03-0000-0001" },
      ],
      construction_works: { 配管工事: ["搬入作業", "溶接"] },
    },
    schedule: [{ id: 1, company: "1班", leader: "佐藤", ext: "1234", outside: "", construction: "", work: "清掃", workers: "" }],
    holiday_rows: [{ id: 5, person: "1班", leader: "佐藤", ext: "1234", outside: "", construction: "", work: "" }],
    equipment: [{ id: 7, equipment: "クレーン", company: "1班", user: "佐藤" }],
    notices: [{ id: 9, text: "", red: false }],
    checked_genres: ["溶接作業"],
  };
}

test("作業予定の欄を、押した値ですぐ書き換える", () => {
  const s = sample();
  assert.equal(applyLocal(s, "PATCH", "/api/schedule/1", { workers: "15" }), true);
  assert.equal(s.schedule[0].workers, "15");
});

test("会社を変えると責任者と内線・外線を空にする（サーバーと同じ決まり）", () => {
  const s = sample();
  applyLocal(s, "PATCH", "/api/schedule/1", { company: "見本電機" });
  assert.deepEqual([s.schedule[0].leader, s.schedule[0].ext, s.schedule[0].outside], ["", "", ""]);
});

test("責任者を選ぶと、登録リストの内線・外線をすぐ出す", () => {
  const s = sample();
  applyLocal(s, "PATCH", "/api/schedule/1", { company: "見本電機", leader: "田中" });
  assert.deepEqual([s.schedule[0].leader, s.schedule[0].ext, s.schedule[0].outside], ["田中", "", "03-0000-0001"]);
  applyLocal(s, "PATCH", "/api/schedule/1", { leader: "手入力の人" });
  assert.deepEqual([s.schedule[0].ext, s.schedule[0].outside], ["", ""]);
});

test("工事件名を変えて、いまの作業内容が選べなくなると空にする", () => {
  const s = sample();
  applyLocal(s, "PATCH", "/api/schedule/1", { construction: "配管工事" });
  assert.equal(s.schedule[0].work, "");
  s.schedule[0].work = "溶接";
  applyLocal(s, "PATCH", "/api/schedule/1", { construction: "配管工事" });
  assert.equal(s.schedule[0].work, "溶接");
  applyLocal(s, "PATCH", "/api/schedule/1", { construction: "塗装工事" }); // 対応表に無い工事件名は、どれでも選べる
  assert.equal(s.schedule[0].work, "溶接");
});

test("休日出勤は所属（person）を変えると責任者を空にする", () => {
  const s = sample();
  applyLocal(s, "PATCH", "/api/holiday-rows/5", { person: "見本電機" });
  assert.equal(s.holiday_rows[0].leader, "");
  applyLocal(s, "PATCH", "/api/holiday-rows/5", { leader: "田中" });
  assert.equal(s.holiday_rows[0].outside, "03-0000-0001");
});

test("機器使用予定は所属を変えると使用者を空にする", () => {
  const s = sample();
  applyLocal(s, "PATCH", "/api/equipment/7", { company: "見本電機" });
  assert.equal(s.equipment[0].user, "");
});

test("連絡事項と作業ジャンル", () => {
  const s = sample();
  applyLocal(s, "PATCH", "/api/notices/9", { text: "避難訓練", red: true });
  assert.deepEqual([s.notices[0].text, s.notices[0].red], ["避難訓練", true]);
  assert.equal(applyLocal(s, "POST", "/api/genres/toggle", { name: "高所作業", checked: true }), true);
  assert.deepEqual(s.checked_genres, ["溶接作業", "高所作業"]);
  applyLocal(s, "POST", "/api/genres/toggle", { name: "溶接作業", checked: false });
  assert.deepEqual(s.checked_genres, ["高所作業"]);
  applyLocal(s, "POST", "/api/genres/toggle", { name: "高所作業", checked: true }); // 二重には入れない
  assert.deepEqual(s.checked_genres, ["高所作業"]);
});

test("先に書き換えられないもの（追加・削除・並べ替え・行が無い）は何もしない", () => {
  const s = sample();
  const before = JSON.stringify(s);
  assert.equal(applyLocal(s, "POST", "/api/schedule", undefined), false);
  assert.equal(applyLocal(s, "DELETE", "/api/schedule/1", undefined), false);
  assert.equal(applyLocal(s, "POST", "/api/schedule/1/move", { direction: "up" }), false);
  assert.equal(applyLocal(s, "PATCH", "/api/schedule/999", { company: "x" }), false);
  assert.equal(applyLocal(null, "PATCH", "/api/schedule/1", { company: "x" }), false);
  assert.equal(JSON.stringify(s), before);
});

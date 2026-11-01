import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5100"


def call(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, method=method, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode("utf-8"))


rows = [
    ("1班", "佐藤", "組み立て作業", "9:00", "15:00", "配管工事"),
    ("見本電機", "田中", "配線工事", "8:00", "18:00", "設備据付工事"),
]
for company, leader, work, start, end, construction in rows:
    rid = call("POST", "/api/schedule")["id"]
    call("PATCH", f"/api/schedule/{rid}", {"company": company, "leader": leader, "work": work, "start_time": start, "end_time": end, "construction": construction})

first_notice = call("GET", "/api/board")["notices"][0]["id"]
call("PATCH", f"/api/notices/{first_notice}", {"text": "本日15時から避難訓練があります", "red": True})
for g in ("溶接作業", "高所作業"):
    call("POST", "/api/genres/toggle", {"name": g, "checked": True})
for w, construction in zip(call("GET", "/api/board")["week_holidays"][:2], ("電気工事", "塗装工事")):
    rid = call("POST", "/api/holiday-rows", {"date": w["date"]})["id"]
    call("PATCH", f"/api/holiday-rows/{rid}", {"person": "1班", "work": "組み立て作業", "start_time": "8:00", "end_time": "17:00", "construction": construction})
print("見本データを入れました")

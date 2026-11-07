#!/usr/bin/env python3
"""毎朝の相場更新。
国際価格（gold-api.com）とドル円（open.er-api.com）から円建て1gの相場を計算し、
純度別の売却価格の目安まで計算して data/latest.json に書く。
係数（お店の内部相場・おすすめの幅など）は環境変数 COEF_JSON から読み、無ければ config.sample.json を使う。
田中貴金属の公表買取価格は照合用に data/compare.csv へ記録するだけで、ページには出さない。
"""
import csv, json, os, re, sys, urllib.request, datetime, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
OZ = 31.1035
TAX = 1.10
JST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(JST)
MODE = sys.argv[1] if len(sys.argv) > 1 else "fix"   # fix = 9:30の確定, est = 明日の目安だけ更新
WD = "月火水木金土日"
def jdate(d, t=""): return f"{d.year}年{d.month}月{d.day}日({WD[d.weekday()]}){t}"

def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "kin-tedori-updater/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def jget(url):
    return json.loads(get(url))

# ---- 係数 ----
coef = json.loads(os.environ.get("COEF_JSON") or (ROOT / "config.sample.json").read_text())

# ---- 国際価格・為替 ----
xau = jget("https://api.gold-api.com/price/XAU")["price"]
xpt = jget("https://api.gold-api.com/price/XPT")["price"]
fx  = jget("https://open.er-api.com/v6/latest/USD")["rates"]["JPY"]

def yen_per_g(usd_oz, adj): return usd_oz / OZ * fx * TAX * adj

# ---- 前回の確定値 ----
latest_path = DATA / "latest.json"
prev = json.loads(latest_path.read_text()) if latest_path.exists() else {}

# ---- 田中貴金属の公表値（照合用。取れなくても止めない）----
tanaka = {}
try:
    html = get("https://gold.tanaka.co.jp/commodity/souba/")
    m = re.search(r"店頭買取価格[^0-9]{0,80}?([0-9,]{5,6})\s*円", html)
    if m: tanaka["au_buy"] = int(m.group(1).replace(",", ""))
    mp = re.search(r"プラチナ.{0,400}?店頭買取価格[^0-9]{0,80}?([0-9,]{4,6})\s*円", html, re.S)
    if mp: tanaka["pt_buy"] = int(mp.group(1).replace(",", ""))
except Exception as e:
    tanaka["error"] = str(e)[:120]

# ---- 補正（大手との差）：照合記録の直近20営業日の平均。無ければ前回値か初期値 ----
cmp_path = DATA / "compare.csv"
def rolling_adj(key, default):
    if not cmp_path.exists(): return default
    rows = list(csv.DictReader(cmp_path.open()))
    vals = [float(r[key]) for r in rows[-20:] if r.get(key)]
    return round(statistics.mean(vals), 4) if len(vals) >= 5 else default

adj_au = rolling_adj("ratio_au", prev.get("adj_au", coef["adj_init"]["au"]))
adj_pt = rolling_adj("ratio_pt", prev.get("adj_pt", coef["adj_init"]["pt"]))

au_now = yen_per_g(xau, adj_au)
pt_now = yen_per_g(xpt, adj_pt)
is_bizday = now.weekday() < 5 and now.strftime("%m-%d") not in coef.get("holidays", [])

if MODE == "fix" and is_bizday:
    base_au, base_pt = au_now, pt_now
    prev_au, prev_pt = prev.get("base_au"), prev.get("base_pt")
    asof = jdate(now, " 9:30 確定")
    # 照合を記録（税抜理論値ではなく税込の値に対する比）
    if tanaka.get("au_buy"):
        theo_au = xau / OZ * fx * TAX
        theo_pt = xpt / OZ * fx * TAX
        newrow = {"date": now.strftime("%Y-%m-%d"), "xau": round(xau,2), "xpt": round(xpt,2), "fx": round(fx,3),
                  "theo_au": round(theo_au), "tanaka_au": tanaka.get("au_buy",""), "ratio_au": round(tanaka["au_buy"]/theo_au, 4),
                  "theo_pt": round(theo_pt), "tanaka_pt": tanaka.get("pt_buy",""),
                  "ratio_pt": round(tanaka["pt_buy"]/theo_pt, 4) if tanaka.get("pt_buy") else ""}
        write_header = not cmp_path.exists()
        with cmp_path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(newrow.keys()))
            if write_header: w.writeheader()
            w.writerow(newrow)
else:
    # 休日や17:00の更新：確定値は前回のまま、明日の目安だけ更新
    base_au, base_pt = prev.get("base_au", au_now), prev.get("base_pt", pt_now)
    prev_au, prev_pt = prev.get("prev_au"), prev.get("prev_pt")
    asof = prev.get("asof", jdate(now))

# ---- 急変の旗：前回確定から持続して大きく動いたか（300円/g以上）----
flag = False
if prev.get("base_au"):
    move = abs(au_now - prev["base_au"])
    last_est = prev.get("est_au")
    # 今回も前回の試算時も同方向に大きく離れていれば「持続した動き」とみなす
    if move >= coef["flag_yen"] and last_est and abs(last_est - prev["base_au"]) >= coef["flag_yen"] * 0.7:
        flag = True

# ---- 純度別の売却価格の目安 ----
rows = []
for p, kind, f in coef["rows"]:
    mb = base_pt if p.startswith("Pt") else base_au
    pub = mb * coef["purity"][p]
    inter = pub * coef["internal"][f]
    lo, hi = coef["band"]["K24"] if p == "K24" else coef["band"]["other"]
    rows.append({"purity": p, "kind": kind, "form": f, "rate": round(pub), "lo": round(inter*lo), "hi": round(inter*hi)})

# 金貨（K24 の計算レート × 重さ に対する幅）
coins=[]
k24_rate = base_au * coef["purity"]["K24"] * coef["internal"]["jewelry"]
for cn in coef.get("coins", []):
    lo, hi = coef["coin_band"]
    coins.append({"name": cn["name"], "g": cn["g"], "lo": round(k24_rate*cn["g"]*lo), "hi": round(k24_rate*cn["g"]*hi),
                  "nobox_lo": round(k24_rate*cn["g"]*lo*coef["coin_nobox"]), "nobox_hi": round(k24_rate*cn["g"]*hi*coef["coin_nobox"])})

# 買取店のHP表示価格（照合・証拠用。店名はページに出さない）
stores = {}
def grab(url, pats):
    try:
        h = get(url); out = {}
        for k, pat in pats.items():
            m = re.search(pat, h)
            if m: out[k] = int(m.group(1).replace(",", ""))
        return out
    except Exception as e:
        return {"error": str(e)[:80]}
stores["A"] = grab("https://goldplaza.jp/gold/rate", {"K24": r'class="_k24[^"]*">([0-9,]+)', "K18": r'class="_k18[^"]*">([0-9,]+)', "K14": r'class="_k14[^"]*">([0-9,]+)', "Pt900": r'class="_pt900[^"]*">([0-9,]+)'})
oh = {}
try:
    h = get("https://www.otakaraya.jp/gold/souba/")
    for m in re.finditer(r'rate-price">([0-9,]+)', h):
        seg = h[max(0, m.start()-2500):m.start()]
        labs = re.findall(r'purity-type">\s*([^<\n]{1,40}?)\s*<', seg)
        lab = labs[-1] if labs else ""
        for key, token in (("K24","24金"),("K18","18金"),("K14","14金"),("Pt900","Pt900")):
            if lab.startswith(token) and key not in oh: oh[key] = int(m.group(1).replace(",", ""))
except Exception as e:
    oh = {"error": str(e)[:80]}
stores["B"] = oh
st_path = DATA / "stores.csv"
if MODE == "fix" and is_bizday:
    row = {"date": now.strftime("%Y-%m-%d")}
    for sid, d in stores.items():
        for k in ("K24","K18","K14","Pt900"): row[f"{sid}_{k}"] = d.get(k, "")
    wh = not st_path.exists()
    with st_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if wh: w.writeheader()
        w.writerow(row)
hp_k24 = [d["K24"] for d in stores.values() if isinstance(d.get("K24"), int)]
hp_range = {"n": len(hp_k24), "max": max(hp_k24), "min": min(hp_k24), "median": sorted(hp_k24)[len(hp_k24)//2]} if hp_k24 else None

# シミュレーション用（係数そのものは出さず、純度×形ごとの「1gあたりの幅」だけ出す）
sim = {}
for p in coef["purity"]:
    mb = base_pt if p.startswith("Pt") else base_au
    pub = mb * coef["purity"][p]
    lo, hi = coef["band"]["K24"] if p == "K24" else coef["band"]["other"]
    sim[p] = {f: {"lo": round(pub*coef["internal"][f]*lo, 1), "hi": round(pub*coef["internal"][f]*hi, 1),
                  "cheap": round(pub*coef["internal"][f]*(lo - coef["cheap_gap"]), 1)} for f in coef["internal"]}

# ---- 今日の動きの文（数字から機械的に）----
def move_text():
    if not prev_au: return "本日の相場を確定しました。"
    d = base_au - prev_au; pct = d / prev_au * 100
    fx_prev, xau_prev = prev.get("fx"), prev.get("xau")
    parts = []
    if fx_prev and xau_prev:
        fx_c = (fx - fx_prev) / fx_prev * 100; au_c = (xau - xau_prev) / xau_prev * 100
        parts.append(f"国際価格は{au_c:+.1f}%、ドル円は{fx - fx_prev:+.2f}円")
    dirw = "高い" if d > 0 else "低い" if d < 0 else "同じ"
    s = f"前日より約{abs(pct):.1f}%{dirw}水準です（{d:+,.0f}円/g）。" if d else "前日とほぼ同じ水準です。"
    if parts: s += " " + "、".join(parts) + "の動きです。"
    return s

memo_path = DATA / "memo.json"
memo = json.loads(memo_path.read_text()) if memo_path.exists() else {}

out = {
    "updated": now.strftime("%Y-%m-%d %H:%M"), "asof": asof, "is_bizday": is_bizday,
    "xau": round(xau, 2), "xpt": round(xpt, 2), "fx": round(fx, 3),
    "adj_au": adj_au, "adj_pt": adj_pt,
    "base_au": round(base_au), "base_pt": round(base_pt),
    "prev_au": round(prev_au) if prev_au else None, "prev_pt": round(prev_pt) if prev_pt else None,
    "est_au": round(au_now), "est_pt": round(pt_now), "est_at": now.strftime("%H:%M"),
    "flag": flag, "flag_yen": coef["flag_yen"],
    "rows": rows, "sim": sim, "stone_per_half_ct": coef["stone_per_half_ct"],
    "coins": coins, "hp_range": hp_range,
    "memo": {"today": move_text(), "short": memo.get("short", ""), "mid": memo.get("mid", ""), "memo_date": memo.get("date", "")},
    "tanaka": tanaka,
}
latest_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))

# 履歴
hist = DATA / "history.csv"
if MODE == "fix" and is_bizday:
    newrow = {"date": now.strftime("%Y-%m-%d"), "base_au": round(base_au), "base_pt": round(base_pt), "xau": round(xau,2), "xpt": round(xpt,2), "fx": round(fx,3)}
    wh = not hist.exists()
    with hist.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(newrow.keys()))
        if wh: w.writeheader()
        w.writerow(newrow)
print(json.dumps({k: out[k] for k in ("asof","base_au","base_pt","est_au","flag","tanaka")}, ensure_ascii=False))

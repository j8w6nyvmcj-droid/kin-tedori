(function(){
  const $ = id => document.getElementById(id);
  const yen = n => Math.round(n).toLocaleString("ja-JP") + "円";
  const chg = (now, prev) => { if (prev == null) return ""; const d = Math.round(now - prev); const s = d > 0 ? "up" : d < 0 ? "down" : "";
    return `<span class="${s}">${d > 0 ? "+" : ""}${d.toLocaleString("ja-JP")}円</span>`; };
  let D = null;
  function render(d){
    D = d;
    $("baseK24").textContent = yen(d.base_au); $("chgK24").innerHTML = chg(d.base_au, d.prev_au); $("estK24").textContent = yen(d.est_au);
    $("basePt").textContent = yen(d.base_pt);  $("chgPt").innerHTML = chg(d.base_pt, d.prev_pt);  $("estPt").textContent = yen(d.est_pt);
    $("asof").textContent = `${d.asof}｜国際価格 ${d.xau.toLocaleString("en-US",{minimumFractionDigits:2})}ドル/オンス、ドル円 ${d.fx.toFixed(2)}円（明日の目安は ${d.est_at} 時点）`;
    $("flag").classList.toggle("on", !!d.flag);
    const t = $("ptable");
    for (const r of d.rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<th>${r.purity}${r.kind ? "<small>" + r.kind + "</small>" : ""}</th><td class="num" style="text-align:right;color:var(--muted)">${yen(r.rate)}</td><td class="c num">${yen(r.lo)} 〜 ${yen(r.hi)}</td>`;
      t.appendChild(tr);
    }
    if (d.hp_range && d.hp_range.n >= 1) {
      const r = d.hp_range; const el = $("hprange");
      el.textContent = `買取店のホームページに出ている参考価格（記録中の${r.n}社・K24）：${r.n > 1 ? yen(r.min) + "〜" : ""}${yen(r.max)}。表示より実際の提示が低いことが多く、理由は下の「読みもの」にあります。`;
      el.hidden = false;
    }
    const ct = $("ctable");
    for (const c of d.coins || []) {
      const div = document.createElement("div"); div.className = "coin";
      div.innerHTML = `<div class="coin-n">${c.name}<span class="coin-g">（純金 ${c.g}g）</span></div>
        <div class="coin-r"><span class="k">箱あり</span><span class="v num">${yen(c.lo)} 〜 ${yen(c.hi)}</span></div>
        <div class="coin-r"><span class="k">箱なし</span><span class="v num e">${yen(c.nobox_lo)} 〜 ${yen(c.nobox_hi)}</span></div>`;
      ct.appendChild(div);
    }
    $("memoToday").textContent = d.memo.today || "";
    $("memoShort").textContent = d.memo.short || "準備中";
    $("memoMid").textContent = d.memo.mid || "準備中";
    $("memoDate").textContent = (d.memo.memo_date ? "短期・中期は " + d.memo.memo_date + " 更新、" : "") + "今日の動きは " + d.updated + " 更新";
  }
  function calc(){
    if (!D) return;
    const p = $("purity").value, f = $("form").value;
    const ct = parseFloat($("stone").value) || 0, stone = ct > 0;
    const w = Math.max(0, (parseFloat($("weight").value) || 0) - ct / 0.5 * D.stone_per_half_ct);
    const offer = parseFloat($("offer").value);
    const s = D.sim[p][f];
    $("range").textContent = `${yen(s.lo * w)} 〜 ${yen(s.hi * w)}`;
    $("perg").textContent = (stone ? `石の分を引いた重さ ${w.toFixed(1)}g` : `${w.toFixed(1)}g`) + ` × 1gあたり ${yen(s.lo)} 〜 ${yen(s.hi)}`;
    $("stoneNote").hidden = !stone;
    const v = $("verdict");
    if (!(offer > 0) || w <= 0) { v.className = "verdict v-fair"; v.textContent = "お店に言われた買取金額を入れると、その金額が高いか安いかの目安が出ます。"; return; }
    const g = offer / w;
    if (g >= s.hi)         { v.className = "verdict v-ok";   v.textContent = "その金額は目安の幅を上回っています。私なら売ります。"; }
    else if (g >= s.lo)    { v.className = "verdict v-fair"; v.textContent = "その金額は目安の幅の中です。売却を考えてよい金額だと思います。"; }
    else if (g >= s.cheap) { v.className = "verdict v-warn"; v.textContent = "その金額は目安の幅を少し下回ります。安くはありませんが、もっと高く買い取るお店があると思います。"; }
    else                   { v.className = "verdict v-bad";  v.textContent = "その金額は目安の幅をかなり下回ります。他のお店にも聞いてみる価値があります。"; }
  }
  $("run").addEventListener("click", calc);
  fetch("data/latest.json?t=" + Date.now()).then(r => r.json()).then(d => { render(d); calc(); })
    .catch(() => { $("asof").textContent = "相場データを読み込めませんでした。しばらくしてから開き直してください。"; });
})();

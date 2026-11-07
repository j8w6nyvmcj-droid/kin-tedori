# 貴金属買取の手取り計算サイト

- `index.html` / `style.css` / `app.js`：ページ本体。`data/latest.json` を読んで表示する
- `scripts/update.py`：毎朝の相場計算。国際価格（gold-api.com）× ドル円（open.er-api.com）× 消費税 × 大手との差の補正
- `data/latest.json`：最新の相場と売却価格の目安（自動生成）
- `data/history.csv`：確定値の履歴、`data/compare.csv`：田中貴金属の公表値との照合記録（ページには出さない）
- `data/memo.json`：市況ひとことの「短期」「中期」（手で更新）
- `config.sample.json`：係数の見本。本番の係数は GitHub の Secrets に `COEF_JSON` として置く
- `.github/workflows/update.yml`：毎日 9:33 と 17:05（日本時間）に自動実行

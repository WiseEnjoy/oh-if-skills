#!/usr/bin/env python3
"""
fill_from_bench.py — 从场景目录的 best（唯一事实源）机械生成表格载荷与可执行 JS
前置: 先跑 refresh_best_mean.py（按 mean<SLA 选优并刷新目录 best/软链接/BEST.md）
本脚本只读不选: scene/best 软链接 → 组合目录 → best.json + best/run-*/bench_stdout.log

字段映射(对齐 ai/jd_model_bench): K=max_concurrency M=num_prompts
  P=mean_ttft_ms Q=mean_tpot_ms R=mean_e2el_ms/1000 S=output_throughput
  T=total_input/duration U=total_token_throughput V=request_throughput
  W=output/(TP×DP)  X=代表轮 bench_stdout.log 原文
输入 rows.json: [{"row":4, "scene_dir":"...", "sla_ms":1000,
                   "expect":{"c0":"FP8","c8":"3.5k","c9":"1.5k"}}]   (expect=行标签校验)
输出: payload.json + write_cells.js(带行标签断言+写入+反向核对) + insert_images.js
用法: python3 fill_from_bench.py rows.json --out <目录>
"""
import json, glob, os, re, sys

COL = {"K":10, "M":12, "P":15, "Q":16, "R":17, "S":18, "T":19, "U":20, "V":21, "W":22}

def main(cfg_path, out_dir="."):
    cfg = json.load(open(cfg_path))
    os.makedirs(out_dir, exist_ok=True)
    rows_out = []
    for row in cfg:
        r0 = row["row"] - 1
        scene = row["scene_dir"].rstrip("/")
        sla_ms = row.get("sla_ms", 1000)
        link = f"{scene}/best"
        if not os.path.islink(link):
            rows_out.append({"row": row["row"], "ok": False, "err": "场景无 best 软链接(先跑 refresh_best_mean.py)"})
            continue
        combo = f"{scene}/{os.readlink(link)}"
        j = json.load(open(f"{combo}/best.json"))
        if j["mean_ttft_ms"] >= sla_ms:
            rows_out.append({"row": row["row"], "ok": False, "err": "best 轮 mean=%.2f 超 SLA" % j["mean_ttft_ms"]})
            continue
        m = re.search(r"-tp(\d+)dp(\d+)-", os.path.basename(combo))
        tp, dp = (int(m.group(1)), int(m.group(2))) if m else (1, 1)
        runs = sorted(glob.glob(f"{combo}/best/run-*/bench_stdout.log"))
        log = open(runs[-1], errors="ignore").read()
        seg = re.search(r"=+ Serving Benchmark Result =+\n.*?\n=+\n", log, re.S)
        seg = seg.group(0).rstrip() if seg else log
        vals = {
            "K": j["max_concurrency"], "M": j["num_prompts"],
            "P": round(j["mean_ttft_ms"], 2), "Q": round(j["mean_tpot_ms"], 2),
            "R": round(j["mean_e2el_ms"] / 1000, 2),
            "S": round(j["output_throughput"], 2),
            "T": round(j["total_input_tokens"] / j["duration"], 2),
            "U": round(j["total_token_throughput"], 2),
            "V": round(j["request_throughput"], 2),
            "W": round(j["output_throughput"] / (tp * dp), 1),
        }
        rows_out.append({
            "row": row["row"], "ok": True, "combo": os.path.basename(combo),
            "expect": row.get("expect", {}), "labels": {"c0": row.get("expect",{}).get("c0",""), "c8": "3.5k", "c9": "1.5k"},
            "cells": [[r0, COL[k], v] for k, v in vals.items()],
            "image": {"row0": r0, "col0": 23, "text": seg},
        })
    payload = {"rows": rows_out}
    with open(f"{out_dir}/payload.json", "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    cells_rows = [{k: v for k, v in r.items() if k != "image"} for r in rows_out]
    with open(f"{out_dir}/write_cells.js", "w") as f:
        f.write(CELLS_JS_TEMPLATE.replace("__PAYLOAD__", json.dumps(cells_rows, ensure_ascii=False)))
    with open(f"{out_dir}/insert_images.js", "w") as f:
        f.write(IMAGES_JS_TEMPLATE.replace("__PAYLOAD__", json.dumps(
            [r["image"] for r in rows_out if r.get("ok")], ensure_ascii=False)))
    print("rows ok:", sum(1 for r in rows_out if r.get("ok")), "/", len(rows_out))

CELLS_JS_TEMPLATE = r'''
(async () => {
  const rows = __PAYLOAD__;
  const ws = APP.getActiveSheet();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const read = (r,c) => { try { const v = APP.getCell(r,c).getValue(); const p = v ? v.private : null; if (p && typeof p === 'object') return String(p.str ?? ''); return String(p); } catch(e) { return ''; } };
  const labelErrs = [], fails = [];
  for (const row of rows) {
    if (!row.ok) continue;
    for (const [ck, want] of Object.entries(row.expect || {})) {
      const got = read(row.row - 1, parseInt(ck.slice(1)));
      if (got !== want) labelErrs.push('行' + row.row + ' 标签' + ck + '=' + got + ' 应=' + want);
    }
  }
  if (labelErrs.length) return JSON.stringify({ABORTED: '行映射校验失败', labelErrs});
  for (const row of rows) {
    if (!row.ok) continue;
    for (const [r, c, v] of row.cells) {
      const want = String(v);
      let okw = false;
      for (let i = 0; i < 4 && !okw; i++) {
        ws.createRange({rowFrom: r, rowTo: r, colFrom: c, colTo: c}).setValue2(v);
        await sleep(120);
        const got = read(r, c);
        okw = (!isNaN(parseFloat(want)) && Math.abs(parseFloat(got) - parseFloat(want)) < 1e-9) || got === want;
      }
      if (!okw) fails.push(r + ':' + c);
    }
  }
  return JSON.stringify({labelErrs: 0, fails, count: fails.length});
})()
'''.strip()

IMAGES_JS_TEMPLATE = r'''
(async () => {
  const images = __PAYLOAD__;
  const ws = APP.getActiveSheet();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const results = [];
  for (const img of images) {
    const ROW = img.row0, COL = img.col0;
    try {
      ws.createRange({rowFrom: ROW, rowTo: ROW, colFrom: COL, colTo: COL}).setValue2('');
      await sleep(800);
      const sv = APP.getActiveSheetView();
      sv.setSelectionRange([{ rowFrom: ROW, rowTo: ROW, colFrom: COL, colTo: COL }], { row: ROW, col: COL });
      await sleep(500);
      const lines = String(img.text).replace(/\r/g, '').split('\n');
      const font = '14px Menlo, Consolas, monospace', LH = 21, PAD = 16;
      const probe = document.createElement('canvas').getContext('2d');
      probe.font = font;
      let w = 0; for (const ln of lines) w = Math.max(w, probe.measureText(ln).width);
      const cv = document.createElement('canvas');
      cv.width = Math.ceil(w) + PAD * 2; cv.height = lines.length * LH + PAD * 2;
      const ctx = cv.getContext('2d');
      ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, cv.width, cv.height);
      ctx.font = font; ctx.fillStyle = '#e6edf3'; ctx.textBaseline = 'top';
      lines.forEach((ln, i) => ctx.fillText(ln, PAD, PAD + i * LH));
      const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
      if (!blob) throw new Error('toBlob null');
      const file = new File([blob], 'r' + ROW + 'c' + COL + '.png', { type: 'image/png' });
      await APP.getUilCmdTool().insertCellPictureFromApi(file, null);
      await sleep(2000);
      results.push('r' + ROW + ':' + (APP.getCell(ROW, COL).isEmpty() ? 'FAIL' : 'OK'));
    } catch (e) { results.push('r' + ROW + ':ERR ' + e.message); }
    await sleep(2000);
  }
  return JSON.stringify(results);
})()
'''.strip()

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else ".")

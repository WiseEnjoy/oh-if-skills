---
name: joyspace-bench-table
description: "把 vbench 测试结果的真实原始数据录入 JoySpace 表格的全流程技能：按 mean TTFT<SLA 口径（对齐 ai/jd_model_bench）自动选优、机械生成载荷与可执行 JS、行标签断言防错位、X 列贴 bench_stdout.log 原文截图。铁律：只录真实原始数据，零人工转录、零手写 JS、零四舍五入自创。触发词：刷新测试表格、bench 结果录入、vllm bench 表格、测试数据落库、最优记录选优。"
---

# joyspace-bench-table（vbench 真实数据 → JoySpace 表格）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `python3` | `command -v python3` | 环境预装，install.sh 自检；两个脚本只用标准库（json/glob/os/re/sys/argparse/shutil/statistics），不需要 pip 装包 |
| `ssh` | `command -v ssh` | 环境预装，install.sh 自检；①② 两步脚本在测试服务器上执行 |
| 内置浏览器 `joycode_browser` | 不走 `command -v` | 内置工具，缺失会在使用点报错，无需预装 |
| JoySpace MCP `read_joyspace` | 不走 `command -v` | 内置 MCP，只用于终验回读，无需预装 |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 铁律（违反任何一条就是事故）

1. **只录真实原始数据**：表格每个数字来自 `best.json`（bench_result.json）原始字段，每张截图是
   `bench_stdout.log` 的 Serving Benchmark Result 段逐字原文。禁止手工转录数字、禁止手写 JS、
   禁止四舍五入自创值（教训：926.71 被写成 927，用户当场判定造假）。
2. **口径写死，人不选择**（2026-11-04 对齐 ai/jd_model_bench 拍板）：
   - SLA 判定 = **mean TTFT < SLA**（不是 P50/P99）
   - P(TTFT)=mean_ttft_ms 原值  Q(TPOT)=mean_tpot_ms  R(E2E)=mean_e2el_ms/1000
   - S(输出吞吐)=output_throughput  T(输入吞吐)=total_input_tokens/duration
   - U(总吞吐)=total_token_throughput  V(QPS)=request_throughput
   - W(单卡)=output_throughput/(TP×DP)，TP/DP 从组合目录名解析，禁止硬编码 8
   - K(最大并发)=max_concurrency  M(总请求数)=num_prompts  X=截图
3. **代表轮必须自身达标**：展示的记录（K-W + X 截图 同一轮）其自身 mean_ttft < SLA；
   档位合并均值达标但代表轮超标的记录禁止入表。
4. **单一事实源**：选优只在 refresh_best_mean.py 做一次（写目录 best/），
   填表脚本只读 best 不再选优——两处选优必然漂移。

## 三步流程（全脚本化）

```bash
# 两个脚本在本技能目录下：<本skill目录>/scripts/（<本skill目录> = skill 工具输出里的
# Base directory for this skill）。在测试服务器上执行，先把 scripts/ 拷过去。
# rows.json 由你按下面 ② 的格式自己写，描述要填哪些行、对应哪个场景目录和 SLA。

# ① 选优（服务器执行；rows.json 同时声明场景目录和 SLA）
python3 refresh_best_mean.py rows.json
# 规则：每档合并全部有效轮(completed==num_prompts)的 ttfts 算 mean，mean<SLA 才合格；
#      单轮有效初判也参与选优；档位吞吐=各轮 output_throughput 中位数；最优=
#      合格档中吞吐最大；代表轮=自身 mean<SLA 的轮中吞吐最高者。输出更新各组合
#      best/、best.json、best_c.txt
#      （文件头自带 judge=mean sla_ms=N 自描述）与场景 best 软链接、BEST.md。

# ② 生成载荷与 JS（服务器执行）
python3 fill_from_bench.py rows.json --out <目录>
# rows.json 每条（expect=行标签校验，不匹配整体中止）：
# {"row":4,"scene_dir":"<场景目录>","sla_ms":1000,
#  "expect":{"c0":"FP8","c8":"3.5k","c9":"1.5k"}}
# 产出 payload.json + write_cells.js + insert_images.js（JS 由脚本生成，禁止手写）

# ③ 执行（office iframe 直开页的浏览器 tab，joycode_browser evaluate）
#    依次执行 write_cells.js 全文（含行标签断言+逐格 verify-retry+反向核对）
#    和 insert_images.js 全文（X 列贴原文截图）；最后 read_joyspace 终验。
```

## 坐标与写入规则（0-based，列号固化）

K=10 M=12 P=15 Q=16 R=17 S=18 T=19 U=20 V=21 W=22 X(截图)=23。
写值用 `ws.createRange({rowFrom,rowTo,colFrom,colTo}).setValue2(v)` + 每格 sleep 120ms 回读重试
（依赖 joyspace-sheet-write 技能的完整写入规范）。
X 列插图用 `APP.getUilCmdTool().insertCellPictureFromApi(file, null)`（依赖 joyspace-sheet-image
技能；选区定位必须 `setSelectionRange([{rowFrom,rowTo,colFrom,colTo}],{row,col})`）。

## 坑点表（全部真实踩过，逐条有事故对应）

| 症状 | 事故 | 处理 |
| --- | --- | --- |
| 表格 TTFT 与截图 Mean TTFT 对不上 | 填了 P50/median 或四舍五入 | P 列=mean_ttft_ms 原值，两位小数原样 |
| 图插到目标格右下一格 | 按旧文档 1-based 传参而 APP 实际 0-based | 一律 0-based（A=0，第 1 行 row=0） |
| insertCellPictureFromApi 正常返回但格子仍空 | setSelectionRange 用 {row,col} 数组元素字段名错误 | 数组元素必须 {rowFrom,rowTo,colFrom,colTo} |
| 行映射错位写错行 | 行号靠记忆 | rows.json 的 expect 行标签校验（c0 格式/c8 输入/c9 输出），不匹配中止 |
| 代表轮 mean 超标 | 合并均值过线但单轮>SLA | 选优规则第 3 条铁律 |
| 图片验证读不到 DISPIMG | getValue/getFormula 懒加载、read_joyspace 不渲染图片 | 用 isEmpty() 判断落库，MCP 不能验证图片 |
| 误插图要清除 | DISPIMG 落错格 | createRange(...).setValue2('') 后 isEmpty 应为 true |
| 单卡吞吐算错 | 硬编码 /8 | 从组合目录名解析 TP×DP |

## 使用前提

- 测试目录结构：`if/<模型>/<场景>/<组合>/{runs/c<N>/run-*,best/,best.json,CONFIG.txt}`，
  best/ 内为代表轮（bench_result.json + bench_stdout.log + meta.txt）。
- 表格对当前账号可编辑，tab 为 office iframe 直开页（APP 可用）。
- 本技能依赖 joyspace-sheet-write（单元格写入规范）与 joyspace-sheet-image（插图规范），
  三者配合使用；本技能只负责"bench 结果→表格"的口径与流程。

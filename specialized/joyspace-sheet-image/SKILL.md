---
name: joyspace-sheet-image
description: "往 JoySpace 在线表格的指定单元格插入图片：把准备好的文本（远程服务器上的脚本内容、bench 汇总输出、日志摘要）用 Canvas 渲染成 PNG，通过 WPS 内部 API insertCellPictureFromApi 一步上传并嵌入表格，单元格落为 DISPIMG 公式；也覆盖单元格写纯文本与读回验证。适用于 JoySpace 表格要求贴日志截图、bench 结果截图、脚本内容截图、DISPIMG 图片列填充。触发词：JoySpace 贴图、插图、插截图、日志截图、bench 截图、单元格图片、贴日志、表格贴图、DISPIMG。"
---

# joyspace-sheet-image（JoySpace 在线表格单元格插图）

## 依赖（首次使用自动安装）

无外部依赖：内置浏览器（`joycode_browser`）+ 系统 `ssh` 取远程文本。截图不靠系统截图工具，
靠在页面里用 Canvas 渲染 PNG，因此无 Screenshot/图形依赖。

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 核心原理（先读这一段，再抄代码）

JoySpace 表格在浏览器里是 WPS 嵌入式表格，没有公开的单元格插图 API，但有内部 JS 对象 `APP`：

| 动作 | API | 说明 |
| --- | --- | --- |
| 定位选区 | `APP.getActiveSheetView().setSelectionRange([单格描述], {row, col})` | `APP.getSheetView()` **不存在**；视图入口是 `getActiveSheetView` |
| 写纯文本 | `APP.getActiveSheetView().getSelectionRange().setValue2(text)` | 前提是已定位选区 |
| 读单元格 | `APP.getCell(row, col).getValue()` | 图片落库后值为 `=DISPIMG("ID_xxx",1)` |
| 插图（唯一正解） | `APP.getUilCmdTool().insertCellPictureFromApi(File, null)` | 写入**当前选区**，一步完成上传+嵌入，返回 Promise |
| 渲染 PNG | `canvas.toBlob('image/png')` → `new File([blob], 'x.png', {type:'image/png'})` | 不依赖系统截图 |

row/col 都是 **0-based** 整数（A=0，X=23，AI=34；第 1 行 row=0），与 `joyspace-sheet-write` 技能一致。例如 AI4（第 4 行 AI 列）= `{row:3, col:34}`。
列号换算（0-based）：`col = (字母部分当 26 进制) - 1`，A=0、Z=25、AA=26、AB=27…；程序里用 `let n=0; for(c of s) n=n*26+(c.charCodeAt(0)-64); n -= 1;`。

## 第一步：取要贴的文本

远程文本用 `ssh` 取回（Docker 容器内文件按 `docker-exec-remote` 的规范执行）；本地文件直接 `cat`。
**返回值不要直接当 evaluate 参数**：超长文本建议先存进一个 shell 变量，再做字符串拼接注入；
JS 里用模板字符串或 `JSON.stringify` 转义，避免引号/换行把代码切断。

若内容过长（>80 行），先与用户确认截断策略（取首尾、取汇总段、全部），不要擅自裁剪。

## 第二步：定位选区 + 渲染 + 插图（完整 JS，直接 evaluate 注入）

把下面整段作为 `joycode_browser` 的 `evaluate` 脚本执行（`ROW/COL/TEXT` 三处替换）：

```js
(async function () {
  const ROW = 3, COL = 34;                 // 目标单元格（AI4 = 0-based row3 col34）
  const TEXT = `替换为要渲染的文本`;      // 反引号里的 \n 会转成换行
  const NAME = `r${ROW}c${COL}.png`;

  // 1) 定位选区到目标单元格
  const sv = APP.getActiveSheetView();
  sv.setSelectionRange([{ rowFrom: ROW, rowTo: ROW, colFrom: COL, colTo: COL }], { row: ROW, col: COL });

  // 2) Canvas 渲染：等宽字体 + 深色底，适合贴日志/代码
  const lines = String(TEXT).replace(/\r/g, '').split('\n');
  const font = '14px Menlo, Consolas, monospace', LH = 21, PAD = 16;
  const probe = document.createElement('canvas').getContext('2d');
  probe.font = font;
  let w = 0; for (const ln of lines) w = Math.max(w, probe.measureText(ln).width);
  const width = Math.ceil(w) + PAD * 2, height = lines.length * LH + PAD * 2;
  const cv = document.createElement('canvas'); cv.width = width; cv.height = height;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, width, height);
  ctx.font = font; ctx.fillStyle = '#e6edf3'; ctx.textBaseline = 'top';
  lines.forEach((ln, i) => ctx.fillText(ln, PAD, PAD + i * LH));

  // 3) Blob -> File -> 一步插入（写当前选区）
  const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
  if (!blob) throw new Error('canvas.toBlob returned null');
  const file = new File([blob], NAME, { type: 'image/png' });
  await APP.getUilCmdTool().insertCellPictureFromApi(file, null);

  // 4) 验证：返回值只回小字符串（大对象会 clone 失败）
  const v = APP.getCell(ROW, COL).getValue();
  return 'inserted -> ' + (typeof v === 'string' ? v.slice(0, 60) : String(v).slice(0, 60));
})()
```

成功标志：返回串里出现 `=DISPIMG("ID_`。跑 `read_joyspace`（MCP 读表）再确认一次服务端已持久化。

## 也可只写纯文本（不插图）

定位选区后 `setValue2`：

```js
(function () {
  const ROW = 3, COL = 34, TEXT = '纯文本内容';   // 0-based，AI4 = row3 col34
  const sv = APP.getActiveSheetView();
  sv.setSelectionRange([{ rowFrom: ROW, rowTo: ROW, colFrom: COL, colTo: COL }], { row: ROW, col: COL });
  sv.getSelectionRange().setValue2(TEXT);
  return 'wrote r' + ROW + 'c' + COL;
})()
```

## 批量插图

逐格调用第二步的函数（每个单元格一次 evaluate；一次塞多张图容易触发上传限流），
相邻两张之间隔 2s（`await new Promise(r => setTimeout(r, 2000))`）。
返回值只收集每格一行状态串，不要返回大对象数组。

## 坑点表（真实踩坑，按错误原文对号入座）

| 症状/错误原文 | 原因 | 处理 |
| --- | --- | --- |
| `l.isValid is not a function` | 调了 `uil.insertPicture({isCellEmbedded:true, cell:{row,col}})`，cell 参数需要内部 Range 对象，普通对象不行 | 一律用 `insertCellPictureFromApi(file, null)`，定位靠前一步的选区 |
| `An object could not be cloned`（evaluate 返回时） | evaluate 返回值过大或含不可结构化对象 | 返回值只回短字符串/小数组（slice 控制长度） |
| `APP.getSheetView is not a function` | 视图入口不叫 getSheetView | 用 `APP.getActiveSheetView()`；sheet 入口是 `APP.getActiveSheet()`（其 Range 有 `select({row,col})` 可定位） |
| 插图成功但单元格公式被覆盖丢失原值 | `=DISPIMG` 公式会替换单元格原值 | 插图前先 `APP.getCell(row,col).getValue()`，非空与用户确认 |
| `canvas.toBlob returned null` | 极少数环境 toBlob 不可用 | 退 `canvas.toDataURL('image/png')` → `fetch(dataURL).blob()` |
| 插入后表格里看不到图、公式在 | 图片异步上传未完成就关页 | 插入后等 Promise resolve 再操作，并在表格里肉眼/再读确认一次 |
| 图插到了目标格的右下一格（行、列都 +1） | 按本技能旧文档的 1-based 传参，而 WPS `APP` 实际是 0-based | row/col 一律 0-based（A=0，第 1 行 row=0），与 `joyspace-sheet-write` 技能一致 |
| `insertCellPictureFromApi` 正常 resolve 但单元格仍是空 | `setSelectionRange([{row, col}])` 数组元素字段名错误，选区没定位上，插图静默落空 | 数组元素必须用 `{rowFrom, rowTo, colFrom, colTo}`（第二个定位参数仍用 `{row, col}`） |
| 插图后 `getValue()`/`getFormula()` 读不到 DISPIMG 公式（返回 undefined 或懒加载对象） | 图片格在部分 WPS 会话里懒加载，值不可直读 | 用 `APP.getCell(r,c).isEmpty()` 判断是否落库（false=成功）；MCP `read_joyspace` 对图片列也显示为空，不能作为图片验证依据 |
| 误插图要清除 | DISPIMG 公式格可被空值覆盖 | `ws.createRange({rowFrom:r,rowTo:r,colFrom:c,colTo:c}).setValue2('')`，然后 `isEmpty()` 应为 true |

## 使用前提

表格 tab 必须由 `joycode_browser` 打开并已加载完（能访问到 `APP` 且 `APP.getActiveBook` 存在）。
`APP` 未定义时：等 2-5s 重试；仍没有则确认 URL 是可编辑的 weboffice 链接（只读预览页没有完整 `APP`）。

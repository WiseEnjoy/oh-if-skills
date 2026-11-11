---
name: joyspace-sheet-write
description: "往 JoySpace 在线表格（WPS 嵌入式）批量写入单元格数据：用 APP.createRange({rowFrom,rowTo,colFrom,colTo}) + setValue2 逐格写入，配 verify-retry 循环防止命令队列丢写；覆盖取可编辑 iframe URL、0-based 索引、合并单元格、数字/文本类型陷阱、read_joyspace 回读校验。触发词：JoySpace 写表格、刷新表格、填表格、批量写单元格、更新 sheet、表格数据落库。"
---

# joyspace-sheet-write（JoySpace 在线表格批量写单元格）

## 依赖（首次使用自动安装）

无外部依赖：内置浏览器（`joycode_browser`）+ JoySpace MCP 的 `read_joyspace`（只读校验）。
JoySpace MCP 目前**没有**单元格写入工具，写操作只能走浏览器里的 WPS 内部 JS 对象 `APP`。

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 核心原理（先读这段，能省一小时）

JoySpace 表格在浏览器里是 WPS 嵌入式表格，单元格读写靠内部 JS 对象 `APP`。
**关键事实：`APP` 只在 office iframe 自己的文档里可用，父页面（joyspace.jd.com）访问不到（跨域）。**

| 动作 | 正确 API | 说明 |
| --- | --- | --- |
| 取表格对象 | `APP.getActiveSheet()` | 返回 worksheet，`getName()` 可确认表名 |
| **取单元格 range** | `ws.createRange({rowFrom, rowTo, colFrom, colTo})` | **唯一正解**，索引 0-based |
| 写值 | `range.setValue2(v)` | 返回 true；写入是异步命令，需回读校验 |
| 读值（可靠） | `APP.getCell(r, c).getValue().private.str` | 0-based；`getValue2()` 在本环境返回 undefined，不可用 |
| 定位选区 | `sv.setSelectionRange([{rowFrom,rowTo,colFrom,colTo}], {row, col})` | 数组元素是 **rowFrom/rowTo/colFrom/colTo**，不是 `{row,col}` |

## 第一步：拿到可编辑的 office iframe URL

1. `joycode_browser open https://joyspace.jd.com/sheets/<pageId>`
2. 在父页面 evaluate 取 iframe 的完整 src（带签名，直接打开即可获得可编辑会话）：

```js
(() => {
  const f = document.getElementById('office-iframe');
  return JSON.stringify({src: f ? f.src : null});
})()
```

3. `joycode_browser open <上一步的 src>` —— 新 tab 里 `window.APP` 才可用。

> 直接拼 `https://joyspace-office.jd.com/weboffice/office/s/<fileId>` 会报 `Invalid URL`（Error 24000），
> 必须带父页面 iframe src 里的 `_w_signature` / `_w_expire_time` / `_x_third_*` 参数。
> 签名有时效，tab 失效后重新走一遍第 1-3 步。

## 第二步：确认坐标与列映射

先用 `read_joyspace`（MCP）拿到表头和行号，再在浏览器里用 `APP.getCell` 抽查 2-3 个已知单元格对齐列号。

```js
(() => {
  const read = (r,c) => {
    try { const cell = APP.getCell(r,c); if(!cell) return '';
      const v = cell.getValue(); if(!v) return '';
      const p = v.private; return p && typeof p === 'object' ? String(p.str ?? '') : String(p);
    } catch(e) { return ''; }
  };
  return JSON.stringify({r3c0: read(3,0), r3c1: read(3,1), r3c3: read(3,3)});
})()
```

`getCell(3,0)` = 第 4 行 A 列（0-based）。列号换算：A=0、B=1 … Z=25、AA=26。

## 第三步：批量写入（必须带 verify-retry）

**裸循环连续 setValue2 会静默丢写**（命令队列合并/丢弃，实测 10 格里只落 2-3 格）。
正确做法：每格写完 sleep ~120ms，回读比对，不一致就重试，最多 4 次。

```js
(async () => {
  const ws = APP.getActiveSheet();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const read = (r,c) => {
    try { const cell = APP.getCell(r,c); if(!cell) return '';
      const v = cell.getValue(); if(!v) return '';
      const p = v.private; return p && typeof p === 'object' ? String(p.str ?? '') : String(p);
    } catch(e) { return ''; }
  };
  const put = async (r, c, v) => {
    const want = String(v);
    for (let i = 0; i < 4; i++) {
      ws.createRange({rowFrom: r, rowTo: r, colFrom: c, colTo: c}).setValue2(v);
      await sleep(120);
      const got = read(r, c);
      if (got === want) return true;
      if (!isNaN(parseFloat(want)) && parseFloat(got) === parseFloat(want)) return true;
    }
    return false;
  };

  // rows: [row0, col0, value] 三元组，按需展开
  const cells = [
    [3, 3, '0.23 release'], [3, 10, 4], [3, 12, 32], [3, 15, 229],
  ];
  const fails = [];
  for (const [r, c, v] of cells) { if (!await put(r, c, v)) fails.push(r + ':' + c); }
  return JSON.stringify({fails, count: fails.length});
})()
```

**分批控制单次 evaluate 时长**：每批 4-5 行（约 40-60 格）为宜，避免 evaluate 超时。

## 第四步：回读校验

写完用 MCP `read_joyspace` 拉一次全表，确认服务端已持久化（浏览器内 `getCell` 有延迟，不能作为最终依据）。

## 坑点表（真实踩坑，按症状对号入座）

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| `setValue2` 返回 true 但值没变 | `ws.getRange(4,4)` 返回的是**整张表**（该函数无参，内部固定取 usedRange） | 用 `ws.createRange({rowFrom,rowTo,colFrom,colTo})` |
| 批量写只落了前几格 | 连续命令被队列合并/丢弃 | 每格 sleep 120ms + 回读重试 |
| `getValue2()` 全返回 undefined | 本环境该 getter 不可用 | 用 `APP.getCell(r,c).getValue().private.str` |
| 读到的值总是上一次写的 | 视图缓存滞后一拍 | 写完 sleep 后再读，或直接以 MCP 回读为准 |
| `setSelectionRange([{row,col}], {row,col})` 后 range 是 -1/-2 | 数组元素字段名不对 | 元素用 `{rowFrom,rowTo,colFrom,colTo}` |
| 写 `"0.30"` 变成 `0.3` | 被当数字解析 | 写 `"0.30 release"` 这类带后缀的文本，或前置 `'` |
| 合并单元格写入报错/无效 | 只能写左上角 | 先确认合并区域，只写 top-left |
| `APP` 未定义 | 在父页面执行（跨域 iframe） | 先取 iframe src 新开 tab，再 evaluate |
| `Invalid URL` / Error 24000 | 手拼 office URL 缺签名 | 从父页面 iframe.src 原样复制 |
| tab 突然不可用（`没有该浏览器页签`） | 浏览器 tab 被回收 | `joycode_browser list` 确认，重新 open |

## 使用前提

- 表格对当前账号有写权限（`APP.session._acl === "write"`、`APP.canEdit() === true`）。
- 目标 tab 是 office iframe 直开页（`APP` 可用），不是 joyspace.jd.com 父页面。
- 写操作前先 `read_joyspace` 读一遍现状，确认目标行列和现有内容，避免覆盖非目标数据。

## 从 vbench 测试结果机械填表（零人工转录）

bench 结果录入 JoySpace 表格的完整口径、选优规则与三步流程见 **joyspace-bench-table** 技能
（scripts/refresh_best_mean.py + fill_from_bench.py 已迁移至该技能）。

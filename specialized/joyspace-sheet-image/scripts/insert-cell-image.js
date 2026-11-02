/*
 * insert-cell-image.js
 * JoySpace 在线表格单元格插图模板（WPS 内部 APP 对象）。
 * 用法：在 joycode_browser 中打开表格 tab，确认页面里能访问 APP 对象后，
 *      把本文件整段作为 evaluate 脚本执行；ROW/COL/TEXT 三处替换为目标值。
 * 注意：evaluate 的返回值会被结构化，只回小字符串（本函数已按此返回）。
 */
(async function () {
  const ROW = 4, COL = 35; // 1-based：AI4 = 第4行、第35列（A=1 … AA=27 … AI=35）
  const TEXT = 'line1\nline2\n替换为要渲染的文本'; // 转 PNG 的内容
  const NAME = 'r' + ROW + 'c' + COL + '.png';

  // 1) 定位选区到目标单元格（插图 API 写当前选区）
  const sv = APP.getActiveSheetView();
  sv.setSelectionRange([{ row: ROW, col: COL }], { row: ROW, col: COL });

  // 2) Canvas 渲染：等宽字体、深色底，适合日志/代码截图
  const lines = String(TEXT).replace(/\r/g, '').split('\n');
  const font = '14px Menlo, Consolas, monospace', LH = 21, PAD = 16;
  const probe = document.createElement('canvas').getContext('2d');
  probe.font = font;
  let w = 0;
  for (const ln of lines) w = Math.max(w, probe.measureText(ln).width);
  const width = Math.ceil(w) + PAD * 2, height = lines.length * LH + PAD * 2;
  const cv = document.createElement('canvas');
  cv.width = width; cv.height = height;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, width, height);
  ctx.font = font; ctx.fillStyle = '#e6edf3'; ctx.textBaseline = 'top';
  lines.forEach((ln, i) => ctx.fillText(ln, PAD, PAD + i * LH));

  // 3) Blob -> File -> 一步插入
  const blob = await new Promise(function (r) { cv.toBlob(r, 'image/png'); });
  if (!blob) throw new Error('canvas.toBlob returned null');
  const file = new File([blob], NAME, { type: 'image/png' });
  await APP.getUilCmdTool().insertCellPictureFromApi(file, null);

  // 4) 验证：只返回小字符串（大对象会 clone 失败）
  const v = APP.getCell(ROW, COL).getValue();
  return 'inserted -> ' + (typeof v === 'string' ? v.slice(0, 60) : String(v).slice(0, 60));
})();

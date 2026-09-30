---
name: opencode-skills-sync
description: "把本机 opencode 全局技能从 ~/.config/opencode/skills 同步到公共 GitHub 仓 WiseEnjoy/oh-if-skills。用户说 同步技能 / 推 skills / GitHub 报 SKILL.md 的 yaml 语法错误 / 修 frontmatter / 更新技能仓 时使用。强制执行 YAML frontmatter 校验与脱敏规则，防止内网域名、IP、真实用户名和路径被推到公网。"
---

# opencode-skills-sync（opencode 全局技能同步 + YAML frontmatter 校验）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| PyYAML | `python3 -c 'import yaml'` | 缺失时 install.sh 执行 pip install pyyaml |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `curl` | `command -v curl` | 环境预装，install.sh 自检 |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。


两侧不是同一份内容，**默认不同步，只在用户要求时同步**，且永远逐文件对比后单向发布：

| | 本地（源） | 公共 GitHub 仓 |
| --- | --- | --- |
| 路径 | `~/.config/opencode/skills/<分类>/<name>/SKILL.md` | `WiseEnjoy/oh-if-skills/<分类>/<name>/SKILL.md` |
| 内容 | 含内网域名、IP、真实用户名、UID、本地路径 | **脱敏占位符版**，供公开分享 |
| 方向 | 权威源，只进不出 | 单向发布，**绝不反向覆盖本地** |


## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `common/user-communication` skill 的 Principles 与 Banned patterns 自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## 一、目录结构与技能契约（2026-09-30 起强制）

1. **两级布局**：`skills/<分类>/<技能名>/SKILL.md`。分类只有两个：
   `common/`（跨任务共性能力：user-communication、safe-ops-rules、long-running-commands）、
   `specialized/`（绑定平台或工具：gitcode-github-pr、ssh-password-transfer、xingyun-push、
   xingyun-reviewer、opencode-skills-sync）。嵌套子目录 opencode 会递归发现（`**/SKILL.md`，实测稳定）。
2. **命名见名知义**：skill `name`、所在目录 basename、正文 h1 标题三者必须一致；
   `name` 只能 `[a-z0-9-]` 且 ≤64 字符，`description` ≤1024 字符（中文 allowed）。
   含糊的旧名要改（`scp-transfer`→`ssh-password-transfer`、`git-pr`→`gitcode-github-pr`、
   `global-skills-sync`→`opencode-skills-sync`、`xllm-pr-autofix`→`xingyun-reviewer`）。
3. **依赖契约**：每个技能目录必须带幂等的 `install.sh`，且 SKILL.md 标题后紧跟
   `## 依赖（首次使用自动安装）` 段——三列 Markdown 表（依赖 / 检查 / 缺失时）+ 一段说明
   「首用先跑 `bash <本skill目录>/install.sh`」。无依赖的技能也保留该段，写明"无外部依赖"。
   新增/改技能时必须同步补这两处，二者描述的依赖必须一致。
4. **输出范式契约**：`user-communication` 不是按需技能，是**所有技能输出都必须服从的元规范**。
   除它自己外，每个 SKILL.md 的依赖段之后必须带一块
   `## 输出范式（所有技能统一）`，指回 `common/user-communication`；
   该技能永远常驻，不按场景取舍。

## 二、YAML frontmatter 硬性规则（GitHub 报 yaml 语法错误的根因）

1. 只有两个字段，顺序固定：`name`、`description`，用 `---` 包裹。
2. `description` **必须整体用双引号**；内部的 `"` 转义成 `\"`。
   未加引号时，值里出现 `: `（冒号+空格，如 `Covers the full loop:`、`Trigger keywords:`）
   会被 YAML 当成新 mapping，GitHub 直接报 `mapping values are not allowed here`。
3. `name`：小写字母/数字/连字符，≤64 字符，与目录名一致。
4. `description`：≤1024 字符，**中文**，写清"什么时候用 + 触发词"，别写成使用教程。
5. **每次改完（新建/编辑）必须跑校验，全绿才算改完**：

```bash
cd ~/.config/opencode/skills
for f in */*/SKILL.md; do python3 - "$f" <<'EOF'
import sys, re, os, yaml
p = sys.argv[1]
t = open(p, encoding='utf-8').read()
m = re.match(r'^---\n(.*?)\n---\n', t, re.S)
assert m, f'{p}: NO FRONTMATTER'
d = yaml.safe_load(m.group(1))
assert re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', d['name']) and len(d['name']) <= 64, f'{p}: bad name'
assert d['name'] == os.path.basename(os.path.dirname(p)), f'{p}: name != dir basename'
assert isinstance(d['description'], str) and len(d['description']) <= 1024, f'{p}: bad description'
assert '## 依赖（首次使用自动安装）' in t, f'{p}: missing dependency section'
assert os.path.isfile(os.path.join(os.path.dirname(p), 'install.sh')), f'{p}: missing install.sh'
if d['name'] != 'user-communication':
    assert '## 输出范式（所有技能统一）' in t, f'{p}: missing output-paradigm block'
print(f'{p:55} OK  name={d["name"]}  desc_len={len(d["description"])}')
EOF
done
```

- 修 frontmatter 只改 `---` 到第二个 `---` 之间，**正文一个字都不要动**。
- 逐字段重新发射即可：`description: ` + `json.dumps(原文, ensure_ascii=False)`（JSON 字符串就是合法 YAML）。

## 三、脱敏对照表（发布到公共仓前逐条套用）

本地有、公共仓必须替换成占位符的内容（**表里不写字面量**，公共仓要能原样发布这张表）：

| 本地有什么 | 公共仓占位符 |
| --- | --- |
| 内网域名：`coding.<内网域名>`、其它公司域名 | `coding<internal-domain>` |
| 内网网段 IP（形如 `11.x.x.x`、`10.x.x.x`） | `<internal-host>` |
| 真实登录名（`ext.<name>`、裸用户名） | `<your-username>` |
| 真实姓名 / 邮箱（commit 的 name、email） | `<your-name>` / `<your-email>` |
| 宿主机共享挂载 UID（`chown`/`chgrp` 里的数字） | `<your-uid>` |
| 真实仓库 / 家目录路径（宿主共享挂载的家目录，形如 `/home/<user>/...`） | `<your-xllm-repo>` / `<your-home-dir>` |
| 内网代理主机名（ProxyCommand 里那个 host） | `<internal-proxy-host>` |

**本地私有字面量清单**：`~/.config/opencode/leak-scan.txt`（**不发布到公共仓**）——
内网域名、内网 IP 网段、真实用户名、UID、真实路径的逐字面量替换对照和发布前 grep 扫描命令。
逐文件脱敏时照它替换；公共仓只保留上面这张通用表。

**禁止 `cp -r` 整目录覆盖**——上次能安全发布靠的就是逐行脱敏；覆盖 = 把内网信息推到公网。
发布后必须在**公共仓**里跑一次清单末尾的扫描命令，0 命中才算干净。

## 四、同步流程

1. 校验本地：跑上面的校验脚本，8 个技能全 OK（`opencode debug skill` 应列出 8 个本地技能）。
2. clone（或复用）公共仓，走 gitcode-github-pr skill 的 GitHub 连通性规则（**去代理直连 + 临时 GIT_CONFIG_GLOBAL**）。
3. `diff <公共仓>/<分类>/<name>/SKILL.md <本地>/<分类>/<name>/SKILL.md`，逐个审阅差异（**目录结构必须先镜像成本地的两级布局**，重命名的技能按新名落位，不保留旧目录）：
   - 只有 frontmatter 引号差异 → 直接修公共仓的 frontmatter；
   - 正文有更新 → 把本地正文搬过去**并套脱敏表**，再 diff 复查有没有漏的内网信息。
4. 在**公共仓**里跑同一套 YAML 校验（脚本里的 `cd` 换成仓库目录），全绿再提交。
5. 提交信息用 `type: 小写描述.` 风格，如 `fix: quote yaml frontmatter descriptions to fix github syntax errors`。
6. push（命令见 gitcode-github-pr skill「clone / push」一节），push 后 `git fetch` 复核远端 sha。
7. 收尾复验：拉 raw URL 再跑一次 YAML 校验——
   `env -u https_proxy curl -sS https://raw.githubusercontent.com/WiseEnjoy/oh-if-skills/main/<分类>/<name>/SKILL.md`。

## 五、常见故障速查

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| GitHub 页面 SKILL.md 报 yaml 错误 | description 含 `: ` 未加引号 | 按第二节修 frontmatter |
| push 报 `CONNECT tunnel failed, response 503` | 走了 `https_proxy` | `env -u https_proxy -u http_proxy` |
| push 到 `gh-proxy.com/...` 报错/只读 | `~/.gitconfig` 的 insteadOf 改写 | `GIT_CONFIG_GLOBAL=<临时config>` 整体替换 |
| `Connection to ssh.github.com closed by remote host` | 本机 SSH 到 GitHub 不可用 | 别修了，直接走 HTTPS（见 gitcode-github-pr skill 的连通性表） |
| push/clone 报 `Failed to connect to github.com port 443` | DNS 解析到不可达 IP（`github.com` 的 A 记录抖动） | `curl --resolve github.com:443:140.82.112.3` 探活，可用就临时写 `/etc/hosts`，push 完删掉 |
| 覆盖公共仓后出现内网信息 | 直接 cp 本地文件 | 立刻 revert，按第三节重新脱敏后再发 |

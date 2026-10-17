---
name: opencode-skills-sync
description: "维护并发布本技能仓：软链接安装模型（三个 agent 的技能目录直接链到仓库克隆，改仓库即生效，不存在本地版与公共版两份）、技能目录契约（name 等于目录名、依赖段 + install.sh、输出范式块、单一权威来源）、YAML frontmatter 硬规则与校验脚本（description 必须整体加双引号，否则 GitHub 报 mapping values are not allowed here）、发布前脱敏扫描与故障速查。触发词：同步技能、推 skills、SKILL.md 报 yaml 语法错误、修 frontmatter、新增技能。"
---

# opencode-skills-sync（opencode 全局技能同步 + YAML frontmatter 校验）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| PyYAML | `python3 -c 'import yaml'` | 缺失时 install.sh 执行 pip install pyyaml |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `curl` | `command -v curl` | 环境预装，install.sh 自检 |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。


软链接模型下两侧**就是同一份内容**（agent 技能目录指向仓库克隆），所以不存在搬运，只有「改仓库 → 脱敏自检 → 提交 push」一条路：

| | 本地（源） | 公共 GitHub 仓 |
| --- | --- | --- |
| 路径 | 各 agent 技能目录里的软链接 → 仓库克隆 | `WiseEnjoy/oh-if-skills/<分类>/<name>/SKILL.md` |
| 内容 | 含内网域名、IP、真实用户名、UID、本地路径 | **脱敏占位符版**，供公开分享 |
| 方向 | 权威源，只进不出 | 单向发布，**绝不反向覆盖本地** |


## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 一、目录结构与技能契约

1. **两级布局**：`<分类>/<技能名>/SKILL.md`。三个分类：`meta/`（元规范，常驻生效）、
   `common/`（跨任务共性能力）、`specialized/`（绑定平台或工具）。
   嵌套子目录 opencode 会递归发现（`**/SKILL.md`，实测稳定）。
   分类归属判据：**被两个以上技能引用的规则放 common，只在一个平台成立的放 specialized。**
2. **命名见名知义**：skill `name`、目录 basename、正文 h1 三者必须一致；
   `name` 只能 `[a-z0-9-]` 且 ≤64 字符，`description` ≤1024 字符（中文 allowed）。
3. **依赖契约**：每个技能目录带幂等 `install.sh`，SKILL.md 标题后紧跟
   `## 依赖（首次使用自动安装）` 段（三列表格 + 一行"首次使用先跑 install.sh"）。
   无依赖的技能也保留该段，写明"无外部依赖"。两处描述的依赖必须一致。
4. **输出范式契约**：除 `user-communication` 自己外，每个 SKILL.md 的依赖段之后带一块
   `## 输出范式（所有技能统一）`，一行回指 `meta/user-communication`。
5. **单一权威来源**：同一条规则只能有一个落点，其他技能只能引用（如分支与 PR 规范统一在
   `common/pr-mr-workflow`）。发现两处写同一规则时，合并到一处再加引用，不许并存。

## 二、YAML frontmatter 硬性规则（GitHub 报 yaml 语法错误的根因）

1. 只有两个字段，顺序固定：`name`、`description`，用 `---` 包裹。
2. `description` **必须整体用双引号**；内部的 `"` 转义成 `\"`。
   未加引号时，值里出现 `: `（冒号+空格，如 `Covers the full loop:`、`Trigger keywords:`）
   会被 YAML 当成新 mapping，GitHub 直接报 `mapping values are not allowed here`。
3. `name`：小写字母/数字/连字符，≤64 字符，与目录名一致。
4. `description`：≤1024 字符，**中文**，写清"什么时候用 + 触发词"，别写成使用教程。
5. **每次改完（新建/编辑）必须跑校验，全绿才算改完**：

```bash
cd <本仓库克隆目录>   # 软链接模型下，权威副本就是仓库工作区
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

**当前安装模型（2026-10-17 起）**：本机三个 agent 的技能目录都是**软链接**，直接指向本仓库克隆
（`~/.joycode/skills/<name>`、`~/.claude/skills/<name>` 为逐技能软链接；
`~/.config/opencode/skills/<分类>` 为分类软链接）。所以：

- 编辑技能 = 直接改仓库工作区文件，三个 agent 下一轮即生效，**不存在"本地版 vs 公共仓版"两份内容**。
- 发布 = 在本仓库提交并 push，不再需要逐文件 diff 搬运。
- **脱敏仍然强制**：新写入的内容里凡是内网域名、内网 IP、真实用户名/姓名/邮箱、UID、
  真实家目录路径，一律按第三节替换成占位符；提交前跑一次扫描，0 命中才能 push。

流程：

1. 改完跑第二节的 YAML 校验脚本，全部技能 OK。
2. 跑脱敏扫描（照 `~/.config/opencode/leak-scan.txt` 的字面量清单 grep），0 命中。
3. 提交信息用 `type: 小写描述.`（≥4 词、句号结尾）。
4. push 按 `gitcode-github-pr` skill 的 GitHub 规则（**去代理直连 + 临时 GIT_CONFIG_GLOBAL + extraHeader**）。
5. push 后 `git fetch` 复核远端 sha 等于本地。

## 五、常见故障速查

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| GitHub 页面 SKILL.md 报 yaml 错误 | description 含 `: ` 未加引号 | 按第二节修 frontmatter |
| push 报 `CONNECT tunnel failed, response 503` | 走了 `https_proxy` | `env -u https_proxy -u http_proxy` |
| push 到 `gh-proxy.com/...` 报错/只读 | `~/.gitconfig` 的 insteadOf 改写 | `GIT_CONFIG_GLOBAL=<临时config>` 整体替换 |
| `Connection to ssh.github.com closed by remote host` | 本机 SSH 到 GitHub 不可用 | 别修了，直接走 HTTPS（见 gitcode-github-pr skill 的连通性表） |
| push/clone 报 `Failed to connect to github.com port 443` | DNS 解析到不可达 IP（`github.com` 的 A 记录抖动） | `curl --resolve github.com:443:140.82.112.3` 探活，可用就临时写 `/etc/hosts`，push 完删掉 |
| 覆盖公共仓后出现内网信息 | 直接 cp 本地文件 | 立刻 revert，按第三节重新脱敏后再发 |

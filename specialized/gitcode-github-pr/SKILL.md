---
name: gitcode-github-pr
description: "在 gitcode.com 和 github.com 上创建、查询、评论、合并 pull request 的完整流程。包含：token 存放与调用方式（不进 URL、不进日志）、fork 跨仓库 PR 的 head/base 方向规则（直接推默认分支、不新建分支）、推前 ls-remote 校验、GitHub 本机连通实测结论（SSH 不可用，只能去代理直连 HTTPS，含 DNS 解析到坏 IP 的处置）、gh CLI 用法，以及三平台统一的 PR 小写标题 + 三段式正文模板。用户说 发起PR / 建PR / 提PR / 合并请求 / 查看PR 时使用。"
---

# gitcode-github-pr（gitcode / github PR 操作）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `curl` | `command -v curl` | install.sh 自动安装 |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `gh` | `command -v gh` | 缺失时 install.sh 从 GitHub releases 下载到 ~/.local/bin |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。


## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `meta/user-communication` skill 的「原则」与「禁止写法」自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## 推送目标（gitcode / github 与行云不同，平台差异硬性规则）

- **行云（coding<internal-domain>）**：同仓库内不同分支做 PR/MR——推 feature 分支，见 xingyun-push skill。
- **gitcode / github**：PR 是**跨仓库**（fork → 上游仓库），**不用新建分支，直接推到本仓库默认分支（main）**；
  PR 的 `head` = fork 的默认分支，`base` = 上游仓库的默认分支。
- 推送后照常 `git ls-remote` 校验远端 sha 与本地一致。

## GitCode（gitcode.com）— xLLM 仓库主平台

- Token：读 `~/.config/opencode/gitcode-token`（600 权限）。**绝不**把 token 打进日志、提交、PR 描述或回显给用户；命令里引用文件即可。
- API base：`https://api.gitcode.com/api/v5`（Gitee v5 兼容）。机器环境自带 `https_proxy`，curl 直接可用。
- owner/repo 从 remote URL 解析：`git remote get-url <name>`，去掉 `git@` / `https://` 前缀与 `.git` 后缀。
- 发 PR 前先确认已推送且远端与本地一致：
  `git ls-remote <remote> refs/heads/<branch>` 的 sha 必须等于本地 `git rev-parse <branch>`。

### 创建 PR

```bash
TOKEN=$(cat ~/.config/opencode/gitcode-token)
curl -s -X POST "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls" \
  -H "Content-Type: application/json" \
  -d "{\"access_token\":\"$TOKEN\",\"title\":\"...\",\"head\":\"<源分支>\",\"base\":\"<目标分支>\",\"body\":\"...\"}"
```

- `head`=fork 默认分支（如 `<fork_owner>:main`），`base`=上游默认分支（如 `main`）。跨仓库方向必须先向用户确认，不猜。
- 成功响应含 `number` 与 `html_url`——把 PR URL 报给用户。

### PR 标题与描述规范（gitcode / github / 行云 三平台统一，团队硬性要求）

**标题**：间接直白、精简准确描述 PR 主题，**纯英文，统一用小写英文单词**
（与行云 MR 一致，推荐 `type: 小写描述.`，如 `bugfix: cap launch blocks for kernels.`；
不要句首大写）。

> **边界**：本规范约束 **PR 标题与描述、提交信息（commit message）、改动代码中的注释**——gitcode/github 的评审侧同样有 agent，会扒**所有**提交面文本做模式匹配：提交信息、代码注释里多一个无关内部名词，都会催生猜测式检视线程。全部按"专业术语 + 实测数据、挤掉无关细节"执行。

**正文三段式**（与行云仓完全一致：h2 标题 + emoji + `-` 列表 + 代码块贴真实输出）：

1. `## 🎯 为什么修改（why）`：先写修改前现状（编号清单——共存的多份实现/多条路径，各自被谁使用），
   再写带来的问题（编号列表），最后写修改后的范围与覆盖清单（哪些场景/模型/模块被覆盖、哪些明确不覆盖）；
   版本、特性等背景要素要写具体。
2. `## 🔧 改了什么（what）`：按使用方视角**自顶向下**分组（每条以加粗小标题开头），每条一句话；
   清理/删除类改动**独立成条并写明原因**；涉及多仓改动时单列一条说明子模块指针前进。
3. `## ✅ 已完成的验证（verified）`：标题用英文过去式（verified，不用 verification）；
   按**算子级/单元级**与**服务级/集成级**分表呈现（列：测试用例 | 结果）；每条结论必须附**真实日志原文**
   （代码块包裹、标注来源文件路径）——无日志或截图佐证的结果不许写进描述；
   测试输出必须**自解释**（不依赖上下文即可读懂），且**不得包含任何本地路径、个人信息、内网地址等敏感信息**。

**格式规范**（三平台统一）：
- 三段标题用 `## 🎯 为什么修改（why）` / `## 🔧 改了什么（what）` / `## ✅ 已完成的验证（verified）`（**h2**；h1 字号过大，不要用 `#`）
- 保留空行与列表版式：压缩字数不许牺牲排版，禁止把内容挤成整段一行式
- **面向读者的表达**：描述写读者能懂的语言——调用者感知不到的内部细节（参数序、符号签名、字段布局、版本演进过程等）**不进描述与注释**，用一句概括代替（如"调用封装与实现 kernel 配套"）。评审方多半也是 agent，只做模式匹配：多写一个内部名词就可能催生一轮猜测式检视线程
- 关联子模块/依赖仓的 PR 链接单独列 `## 🔗 关联子模块 PR` 节
- 可用 emoji 增强可读性：🔧 改动、✅ 通过、📊 数据、⚠️ 注意

**创建纪律**：用户说"起草"= 只要草稿；对稿子的任何修改意见（包括改标题）都**不等于创建授权**；
必须等用户对最终稿明确说"可以创建/确认提交"才可创建 PR。误创建立即关闭并说明。

生成 PR body 时按此结构起草，贴给用户确认后再提交。

### 查询 / 评论 / 合并

> **回复评论同样执行专业化规范**：专业术语 + 实测数据，挤掉无关细节；调用者感知不到的内部机制一个名词都不写——对方 agent 会扒 PR 全部文本，回复里的多余名词就是下一轮猜测线程的素材。

```bash
# 列出 open PR
curl -s "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls?state=open&access_token=$TOKEN"
# PR 详情（含 body、state、diff_url）
curl -s "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls/<number>?access_token=$TOKEN"
# PR 评论
curl -s "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls/<number>/comments?access_token=$TOKEN"
# 改动文件列表
curl -s "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls/<number>/files?access_token=$TOKEN"
```

- 合并 PR 用 `PUT /repos/<owner>/<repo>/pulls/<number>/merge`（body 可带
  `merge_method`）；先 GET 详情确认 `state` 为 open、无冲突再执行。
- 若某端点返回 404/405，说明 gitcode 未实现该 v5 子集——改用网页 URL 交由用户操作，不要盲试。

## GitHub 平台

### 连通性硬规则（本机实测，别再逐个试）

| 通道 | 实测结果 | 结论 |
| --- | --- | --- |
| SSH `git@github.com`（`~/.ssh/config` 走 `<internal-proxy-host>` ProxyCommand） | 握手 + publickey 认证成功，随即远端断会话：`Connection to ssh.github.com closed by remote host` | **不可用**，git over SSH 放弃 |
| SSH 直连 22 或 `ssh.github.com:443`（去掉 ProxyCommand） | `Bad packet length ... Connection corrupted`（链路注入） | **不可用** |
| HTTPS 走环境 `https_proxy`（`<internal-proxy-host>`） | `CONNECT tunnel failed, response 503`（`github.com` 不在放行名单） | **不可用** |
| HTTPS 去掉代理直连 `github.com` | 正常 | **clone / fetch / push / raw / API 一律用这条** |

- **DNS 偶发解析到不可达 IP**（实测 2026-09-30：`github.com` → `20.205.243.166` TCP 443 不通，
  而 `api.github.com` 的 `20.205.243.168` 和 `140.82.112.x` 都通）。表现：clone/push 报
  `Failed to connect to github.com port 443 after N ms` 或 `Failure when receiving data from the peer`。
  处理：`env -u https_proxy curl -sS -o /dev/null -w '%{http_code}' --resolve github.com:443:140.82.112.3 https://github.com/`
  探活，通了就把该 IP 临时追加到 `/etc/hosts`（`140.82.112.3 github.com`），push 完删掉——
  **用完必须删**，否则 IP 轮换后会踩新的坑；多个 IP 逐个试（140.82.112.x / 113.x / 114.x）。
- `api.github.com` 两种通道都通；`gh-proxy.com` 只读下载代理，只能 clone 公开仓，**不能 push**。
- 环境 `https_proxy` 对 gitcode 正常、对 github push 会 503——GitHub 操作统一 `env -u https_proxy -u http_proxy -u HTTPS_PROXY -u HTTP_PROXY`。

### Token 与认证

- PAT 存 `~/.config/opencode/github-token`（600，与 `gitcode-token` 同规）；缺失时向用户要，**不要**去日志里翻。
- **绝不**把 token 拼进 remote URL、命令回显、日志、commit、PR 描述；一律用 `-c http.extraHeader`（token 不进 URL、不进 `.git/config`）。

### clone / push（必须同时绕开 gh-proxy 改写 + 去代理）

`~/.gitconfig` 有 `url.https://gh-proxy.com/github.insteadof=https://github`，会把 push 也改写到只读代理，
所以用临时 global config 整体替换掉全局配置：

```bash
TOKEN=$(cat ~/.config/opencode/github-token)
AUTH=$(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)
printf '[user]\n\tname = <your-name>\n\temail = <your-email>\n[safe]\n\tdirectory = *\n' > /tmp/oc-gitconfig

# clone
env -u https_proxy -u http_proxy GIT_CONFIG_GLOBAL=/tmp/oc-gitconfig \
  git clone https://github.com/<owner>/<repo>.git

# push
env -u https_proxy -u http_proxy GIT_CONFIG_GLOBAL=/tmp/oc-gitconfig \
  git -c http.extraHeader="Authorization: Basic $AUTH" push origin HEAD:main

# API
env -u https_proxy -u http_proxy curl -sS -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/<owner>/<repo>
```

- push 后必须复核：`git fetch` 后 `git rev-parse origin/<branch>` 等于本地 sha，或直接打 raw URL 复验内容。
- API 频率：匿名 60 次/时、带 token 5000 次/时——批量查询先带 token，别裸调。
- `git ls-remote` 也要在 `env -u https_proxy` 下跑，否则同样 503。

### gh CLI 用法

- 已装在 `~/.local/bin/gh`（aarch64）。先 `export PATH="$HOME/.local/bin:$PATH"`；若不存在，
  从 `https://github.com/cli/cli/releases` 下载 `gh_<ver>_linux_<arch>.tar.gz`，
  取出 `bin/gh` 放入 `~/.local/bin`（下载慢/被截断时用 `curl --retry -C -` 断点续传）。
- **当前未 `gh auth login`**，认证直接给环境变量：`GH_TOKEN=$(cat ~/.config/opencode/github-token) gh ...`；
  gh 自身也要 `env -u https_proxy` 才能连上。
- 常用：

```bash
export PATH="$HOME/.local/bin:$PATH"
# 跨仓库 PR：直接推 fork 默认分支，不新建分支
gh pr create --repo <上游 owner>/<repo> --base main --head <fork_owner>:main \
  --title "bugfix: 小写英文描述." --body "..."
gh pr list --repo <owner>/<repo>
gh pr view <number> --repo <owner>/<repo> --json number,title,state,url
gh pr merge <number> --repo <owner>/<repo> --merge   # 或 --squash/--rebase
```

- release 下载失败就重试或改用带 token 的 API，不要长时间重试同一条死路（连通性表见上）。

## 流程约定

1. 先 `git status` / `git log` 确认要进 PR 的提交，未提交改动先问用户是否包含。
2. gitcode/github：**直接推到本仓库默认分支（main），不新建分支**（跨仓库 PR，head=fork 默认分支）；
   行云：推 feature 分支后同仓库建 MR（见 xingyun-push skill）。
3. 推送 → `ls-remote` 校验 → 按「PR 标题与描述规范」起草（小写标题 + 行云三段式正文）→ 用户确认 → 建 PR。
4. head/base 有歧义时（多个 remote、多个仓库同名）必须向用户确认，不猜。
5. 平台钩子会校验提交信息；向 xingyun（coding<internal-domain>）推代码时遵循 xingyun-push skill。

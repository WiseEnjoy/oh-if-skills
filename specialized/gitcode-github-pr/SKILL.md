---
name: gitcode-github-pr
description: "gitcode.com 与 github.com 的 PR 操作：token 存放与调用（不进 URL、不进日志，且不是 git 操作的默认前提）、fork 跨仓库 head/base 方向、gh CLI 用法，以及 clone/push 失败后的排障——连通性与代理绕行（去代理直连、临时 GIT_CONFIG_GLOBAL 绕 gh-proxy 改写、坏 IP 的 DNS 处置）属于特定内网环境的实测结论，默认先按常规方式推，失败了再判断是否适用。分支生命周期与 PR 标题正文规范见 common/pr-mr-workflow。触发词：发起PR、建PR、提PR、查看PR、合并请求。"
---

# gitcode-github-pr（gitcode / github PR 操作）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `curl` | `command -v curl` | install.sh 自动安装 |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `gh` | `command -v gh` | 缺失时 install.sh 从 GitHub releases 下载到 ~/.local/bin |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。


## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 分支风格与 PR 方向

分支生命周期与提交组织见 `common/pr-mr-workflow`。这两个平台的差异只有三点：

- remote 约定：`origin` = 自己的 fork，`upstream` = 上游仓库（没有就
  `git remote add upstream https://<host>/<上游owner>/<repo>.git`）。
- PR 是**跨仓库**：`feat/<name>` 推到 fork，PR 的 `head` = `<fork_owner>:feat/<name>`，
  `base` = 上游默认分支。**fork 的 main 不用维护**，过期没关系。
- 这两个平台**没有**行云式服务端钩子，但提交消息仍用同一格式，三平台保持一致。

推送后必须 `git ls-remote <remote> refs/heads/<branch>` 校验远端 sha 等于本地 `git rev-parse <branch>`。

## GitCode（gitcode.com）— xLLM 仓库主平台

- Token：读本机私有文件（600 权限），路径用 `TOKEN_FILE` 指向实际位置（历史位置 `~/.config/<agent>/gitcode-token`）；缺失时向用户要。**绝不**把 token 打进日志、提交、PR 描述或回显给用户；命令里引用文件即可。
- API base：`https://api.gitcode.com/api/v5`（Gitee v5 兼容）。机器环境自带 `https_proxy`，curl 直接可用。
- owner/repo 从 remote URL 解析：`git remote get-url <name>`，去掉 `git@` / `https://` 前缀与 `.git` 后缀。
- 发 PR 前先确认已推送且远端与本地一致：
  `git ls-remote <remote> refs/heads/<branch>` 的 sha 必须等于本地 `git rev-parse <branch>`。

### 创建 PR

```bash
TOKEN=$(cat "$TOKEN_FILE")
curl -s -X POST "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls" \
  -H "Content-Type: application/json" \
  -d "{\"access_token\":\"$TOKEN\",\"title\":\"...\",\"head\":\"<源分支>\",\"base\":\"<目标分支>\",\"body\":\"...\"}"
```

- `head`=fork 上的特性分支（如 `<fork_owner>:feat/<name>`），`base`=上游默认分支（如 `main`）。跨仓库方向必须先向用户确认，不猜。
- 成功响应含 `number` 与 `html_url`——把 PR URL 报给用户。

### PR 标题与描述

见 `common/pr-mr-workflow`（标题、三段式正文、格式规范、创建纪律四项三平台通用）。
生成 body 后贴给用户确认再提交。

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

### 连通性：默认按常规方式走，失败了再查下面的环境专有处置

**默认动作**：直接用仓库现有 remote 和全局 git 配置 `git clone` / `git push` / `git fetch`，
**不要预先套任何绕行**（不加 `env -u https_proxy`、不换临时 `GIT_CONFIG_GLOBAL`、不加 extraHeader）。
通了就结束。

**只有常规方式真的报错时**，才拿错误信息到下面两节对号入座。下面的结论**绑定具体环境**，
不是本技能的默认前提——照着预先套，就会把一条通路改成不通，或者把简单操作搞成一串绕行命令。

> 反例（2026-11-11，macOS 宿主机）：`origin` 是 `git@github.com:...` 的 SSH remote，
> `git push --force-with-lease origin main` 一次成功（走用户的全局代理配置）。
> 此前曾按下表预先判定"SSH 不可用、必须去代理直连 + 临时 config + extraHeader"并据此向用户
> 给出整套绕行命令——**那是把别的环境的实测当成了本机结论**，用户当场纠正。
> 教训：连通性属于环境事实，必须先试后断言；没在当前环境跑过，就不要向用户陈述为结论。

#### 环境专有现象（内网 Linux 容器 / opencode 环境实测，**非通用**）

| 通道 | 该环境实测结果 | 该环境下的结论 |
| --- | --- | --- |
| SSH `git@github.com`（`~/.ssh/config` 走 `<internal-proxy-host>` ProxyCommand） | 握手 + publickey 认证成功，随即远端断会话：`Connection to ssh.github.com closed by remote host` | 该环境不可用，改走 HTTPS |
| SSH 直连 22 或 `ssh.github.com:443`（去掉 ProxyCommand） | `Bad packet length ... Connection corrupted`（链路注入） | 该环境不可用 |
| HTTPS 走环境 `https_proxy`（`<internal-proxy-host>`） | `CONNECT tunnel failed, response 503`（`github.com` 不在放行名单） | 该环境不可用 |
| HTTPS 去掉代理直连 `github.com` | 正常 | **该环境**的 clone / fetch / push / raw / API 走这条 |

- **DNS 偶发解析到不可达 IP**（实测 2026-09-30：`github.com` → `20.205.243.166` TCP 443 不通，
  而 `api.github.com` 的 `20.205.243.168` 和 `140.82.112.x` 都通）。表现：clone/push 报
  `Failed to connect to github.com port 443 after N ms` 或 `Failure when receiving data from the peer`。
  处理：`env -u https_proxy curl -sS -o /dev/null -w '%{http_code}' --resolve github.com:443:140.82.112.3 https://github.com/`
  探活，通了就把该 IP 临时追加到 `/etc/hosts`（`140.82.112.3 github.com`），push 完删掉——
  **用完必须删**，否则 IP 轮换后会踩新的坑；多个 IP 逐个试（140.82.112.x / 113.x / 114.x）。
  DNS 抖动期 `raw.githubusercontent.com` 直连同样超时——复验不必死磕直连：
  **fetch 走 origin 的 gh-proxy URL**（环境代理下稳定，且能下载真实对象核对 sha），
  raw 走 gh-proxy 镜像 `https://gh-proxy.com/https://raw.githubusercontent.com/...`。
- 该环境下 `api.github.com` 两种通道都通；`gh-proxy.com` 作为只读下载代理只能 clone 公开仓，
  当时实测不能 push（**此结论也只对那个环境成立，别拿它去否定用户机器上的代理配置**）。
- 该环境 `https_proxy` 对 gitcode 正常、对 github push 会 503，所以那里的 GitHub 操作要
  `env -u https_proxy -u http_proxy -u HTTPS_PROXY -u HTTP_PROXY`；其他环境不要默认加。

### Token 与认证

- PAT 同样存本机私有文件（600），用 `TOKEN_FILE` 指向；缺失时向用户要，**不要**去日志里翻。
- **绝不**把 token 拼进 remote URL、命令回显、日志、commit、PR 描述。
- **token 不是 git 操作的默认前提**：SSH remote、credential helper、用户自己的代理配置都可能让
  `git push` 直接成功，此时一个 token 都不需要。**先试常规 push**；只有在报
  `could not read Username`、`Authentication failed`、`403` 这类凭据错误时才取 token，
  并且用 `-c http.extraHeader`（token 不进 URL、不进 `.git/config`）。
- 已知的凭据失败场景：credential helper（VS Code remote-containers）注册在 `~/.gitconfig`，
  **交互式终端**能用，**非交互 shell**（opencode 等）下取不到（实测 `could not read Username`）——
  这种情况才用 token 文件 + extraHeader。

### clone / push 失败后的绕法（环境专有，默认不要用）

**先跑 `git push origin <branch>` / `git clone <url>`；成功就到此为止，下面这套一行都不要用。**

只有在常规方式失败、且失败原因对上了上面那张环境表时才用这套。它针对的是这样一个环境：
`~/.gitconfig` 里有 `url.https://gh-proxy.com/github.insteadof=https://github`，把 push 也改写到
只读代理，同时环境 `https_proxy` 对 github 返回 503——所以要用临时 global config 整体替换全局配置：

```bash
TOKEN=$(cat "$TOKEN_FILE")
AUTH=$(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')
printf '[user]\n\tname = <your-name>\n\temail = <your-email>\n[safe]\n\tdirectory = *\n' > /tmp/oc-gitconfig

# clone
env -u https_proxy -u http_proxy GIT_CONFIG_GLOBAL=/tmp/oc-gitconfig \
  git clone https://github.com/<owner>/<repo>.git

# push（feat/<name> 推到 fork，不动 fork 的 main）
env -u https_proxy -u http_proxy GIT_CONFIG_GLOBAL=/tmp/oc-gitconfig \
  git -c http.extraHeader="Authorization: Basic $AUTH" push origin feat/<name>

# API
env -u https_proxy -u http_proxy curl -sS -H "Authorization: Bearer $TOKEN" \
  https://api.github.com/repos/<owner>/<repo>
```

- push 后必须复核：`git fetch` 后 `git rev-parse origin/<branch>` 等于本地 sha，或直接打 raw URL 复验内容。
- API 频率：匿名 60 次/时、带 token 5000 次/时——批量查询先带 token，别裸调。
- 用了这套绕法时，`git ls-remote` 也要在同样的 `env -u https_proxy` 下跑，否则同样 503。
- `base64 -w0` 是 GNU 写法，**macOS 上没有 `-w`**（报 `invalid option`）——跨环境统一写
  `| base64 | tr -d '\n'`。

### gh CLI 用法

- 已装在 `~/.local/bin/gh`（aarch64）。先 `export PATH="$HOME/.local/bin:$PATH"`；若不存在，
  从 `https://github.com/cli/cli/releases` 下载 `gh_<ver>_linux_<arch>.tar.gz`，
  取出 `bin/gh` 放入 `~/.local/bin`（下载慢/被截断时用 `curl --retry -C -` 断点续传）。
- **当前未 `gh auth login`**，认证直接给环境变量：`GH_TOKEN=$(cat "$TOKEN_FILE") gh ...`；
  gh 自身也要 `env -u https_proxy` 才能连上。
- 常用：

```bash
export PATH="$HOME/.local/bin:$PATH"
# 跨仓库 PR：head 用 fork 上的 feat 分支，base 用上游默认分支
gh pr create --repo <上游 owner>/<repo> --base main --head <fork_owner>:feat/<name> \
  --title "bugfix: 小写英文描述." --body "..."
gh pr list --repo <owner>/<repo>
gh pr view <number> --repo <owner>/<repo> --json number,title,state,url
gh pr merge <number> --repo <owner>/<repo> --merge   # 或 --squash/--rebase
```

- release 下载失败就重试或改用带 token 的 API，不要长时间重试同一条死路（连通性表见上）。

## 流程约定

1. 先 `git status` / `git log` 确认要进 PR 的提交，未提交改动先问用户是否包含。
2. 分支风格三平台统一（见「分支风格」节）：一切工作在 `feat/<name>` 分支、本地 main 零提交、合入后删分支；
   差异只在 PR 方向——行云同仓库分支 MR（见 xingyun-push skill），
   gitcode/github 跨仓库（head=`<fork_owner>:feat/<name>`，base=上游 main）。
3. 推送 → `ls-remote` 校验 → 按「PR 标题与描述规范」起草（小写标题 + 行云三段式正文）→ 用户确认 → 建 PR。
4. head/base 有歧义时（多个 remote、多个仓库同名）必须向用户确认，不猜。
5. 平台钩子会校验提交信息；向 xingyun（coding<internal-domain>）推代码时遵循 xingyun-push skill。

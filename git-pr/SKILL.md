---
name: git-pr
description: "Create, list, view and merge pull requests on gitcode.com (OpenAPI, Gitee-v5 style) and github.com (gh CLI). Use when the user asks to 发起PR / 建PR / 提PR / 合并请求 / 创建 pull request / MR, list or inspect PRs, or merge a PR on gitcode or github. Covers token handling, fork-based PR flow, and branch-push-before-PR checks."
---

# git-pr (gitcode / github PR operations)

## GitCode (gitcode.com) — xLLM 仓库主平台

- Token：读 `~/.config/opencode/gitcode-token`（600 权限）。**绝不**把 token 打进日志、提交、PR 描述或回显给用户；命令里引用文件即可。
- API base：`https://api.gitcode.com/api/v5`（Gitee v5 兼容）。机器环境自带 `https_proxy`，curl 直接可用。
- owner/repo 从 remote URL 解析：`git remote get-url <name>`，去掉 `git@` / `https://` 前缀与 `.git` 后缀。
- 发 PR 前先确认分支已推送且远端与本地一致：
  `git ls-remote <remote> refs/heads/<branch>` 的 sha 必须等于本地 `git rev-parse <branch>`。

### 创建 PR

```bash
TOKEN=$(cat ~/.config/opencode/gitcode-token)
curl -s -X POST "https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls" \
  -H "Content-Type: application/json" \
  -d "{\"access_token\":\"$TOKEN\",\"title\":\"...\",\"head\":\"<源分支>\",\"base\":\"<目标分支>\",\"body\":\"...\"}"
```

- `head`=源分支，`base`=目标分支。多 remote / fork 场景必须先向用户确认方向
  （典型 xLLM 流程：push 到 fork `zh`，然后对上游仓库发 PR，此时 POST 到上游，
  并加 `"head_repo":"<fork_owner>/<repo>"`）。
- 成功响应含 `number` 与 `html_url`——把 PR URL 报给用户。

### PR 标题与描述规范（gitcode / github / 行云 三平台统一，团队硬性要求）

**标题**：间接直白、精简准确描述 PR 主题，**纯英文**。

> **边界**：本规范只约束 **PR 标题与描述**。**提交信息（commit message）不受此约束**，
> 继续沿用行云提交规范（`type: xxx.` 格式，见 xingyun-push skill）；两者互不影响。

**正文三段式**（内容用中文，便于理解）：

1. **为什么修改**：写清楚背景和原因，讲 **why**。
2. **修改的内容**：讲 **what**（做了哪些改动、涉及哪些组件）。
3. **修改后的效果**：说明可达成预期目标、不引入新问题、不对无关场景产生副作用；
   可附测试结果——测试结果必须**自解释**（不依赖上下文即可读懂），且**不得包含任何本地路径、
   个人信息、内网地址等敏感信息**。

生成 PR body 时按此结构起草，贴给用户确认后再提交。

### 查询 / 评论 / 合并

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

## GitHub

- gh CLI 安装在 `~/.local/bin/gh`（aarch64）。先 `export PATH="$HOME/.local/bin:$PATH"`；若不存在，
  按机器架构从 `https://github.com/cli/cli/releases` 下载对应 `gh_<ver>_linux_<arch>.tar.gz`，
  取出 `bin/gh` 放入 `~/.local/bin`（下载慢/被截断时用 `curl --retry -C -` 断点续传）。
- 认证用环境变量（不要永久落盘，除非用户要求）：`GH_TOKEN=<token> gh ...`
- 常用：

```bash
export PATH="$HOME/.local/bin:$PATH"
gh pr create --repo <owner>/<repo> --base <target> --head <source-branch> \
  --title "..." --body "..."
gh pr list --repo <owner>/<repo>
gh pr view <number> --repo <owner>/<repo> --json number,title,state,url
gh pr merge <number> --repo <owner>/<repo> --merge   # 或 --squash/--rebase
```

- 环境已有 `https_proxy`，gh 走代理即可；若 release 下载失败可重试或请用户提供 token 后用 API 代替。

## 流程约定

1. 先 `git status` / `git log` 确认要进 PR 的提交，未提交改动先问用户是否包含。
2. 推分支（fork 场景推到 fork remote）→ `ls-remote` 校验 → 按「PR 标题与描述规范」起草 → 用户确认 → 建 PR。
3. head/base 有歧义时（多个 remote、多个分支同名）必须向用户确认，不猜。
4. 平台钩子会校验提交信息；向 xingyun（coding<internal-domain>）推代码时遵循 xingyun-push skill。

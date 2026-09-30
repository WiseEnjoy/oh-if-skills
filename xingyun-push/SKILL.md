---
name: xingyun-push
description: "Use when pushing to the JD internal Xingyun repo (coding<internal-domain>:xLLM_AI/xllm.git), rebasing onto its main, creating commits that must pass the platform push rules, creating PRs/MRs on Xingyun, or troubleshooting coding<internal-domain> fetch/push failures (message-format rejections, transfer corruption, submodule validator blocks)."
---

# Xingyun Push (星云仓 rebase / 提交 / 推送规范)

Distilled from real push failures on `coding<internal-domain>:xLLM_AI/xllm.git`. Follow
these rules exactly — the platform enforces them with server-side hooks.

## Identity (提交身份)

Verify before committing (repo-local config, already set):

```
user.name  = <your-name>
user.email = <your-email>
```

## Commit message format (平台钩子强制)

The Xingyun push hook validates **every commit in the push payload** against:

```
^(feat|bugfix|docs|test|refactor|chore|style|revert|perf|model|build|skills): (\S+ ){3,}\S+\.$
```

Rules:

1. Type MUST be one of: `feat|bugfix|docs|test|refactor|chore|style|revert|perf|model|build|skills`.
   `fix:` is **rejected** — use `bugfix:`.
2. Description: at least 4 space-separated words, MUST end with a period.
3. **Title-only, NO body.** Multi-line bodies fail the hook (it matches the
   whole message, not just the first line).
4. No `(#N)` suffix after the period (mainline commits like
   `... pool counts. (#168)` do NOT pass — never introduce new ones).

## The trailing-newline trap (提交信息尾部换行)

Git always stores `"title\n"`. The hook's regex uses strict end-of-text `$`
semantics, so **every normally-created commit is rejected** with
`'<sha>' 中的提交信息不符合格式要求`, even when the title looks compliant
(verified by probe: the same text without the trailing newline passes).

Workaround — rebuild commits via `git commit-tree` with the trailing newline
stripped, preserving tree / parents / author / committer:

```bash
# Rewrite NEW..OLD-TIP commits to newline-less messages, in order.
prev=<new-base>            # e.g. the commit the chain sits on
for sha in <sha1> <sha2> <sha3>; do
  tree=$(git rev-parse "$sha^{tree}")
  an=$(git log -1 --format=%an $sha); ae=$(git log -1 --format=%ae $sha)
  ad=$(git log -1 --format=%aD $sha)
  cn=$(git log -1 --format=%cn $sha); ce=$(git log -1 --format=%ce $sha)
  cd=$(git log -1 --format=%cD $sha)
  msg=$(git log -1 --format=%B $sha | python3 -c "import sys; sys.stdout.write(sys.stdin.read().rstrip('\n'))")
  new=$(printf '%s' "$msg" | GIT_AUTHOR_NAME="$an" GIT_AUTHOR_EMAIL="$ae" \
        GIT_AUTHOR_DATE="$ad" GIT_COMMITTER_NAME="$cn" \
        GIT_COMMITTER_EMAIL="$ce" GIT_COMMITTER_DATE="$cd" \
        git commit-tree "$tree" -p "$prev")
  echo "$sha -> $new"; prev=$new
done
git push --force-with-lease coding $prev:refs/heads/<branch>
```

Pre-check locally before pushing:

```python
import re, subprocess
pat = re.compile(r'^(feat|bugfix|docs|test|refactor|chore|style|revert|perf|model|build|skills): (\S+ ){3,}\S+\.$')
full = subprocess.run(['git','log','-1','--format=%B',sha],capture_output=True,text=True).stdout.rstrip('\n')
assert pat.match(full)
```

## Rebase onto Xingyun main

```bash
git fetch coding main
git rebase coding/main
```

Network / toolchain quirks (all encountered for real):

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Bad owner or permissions on /root/.ssh/config` | ownership reverts to UID <your-uid> | `chown -R root:root /root/.ssh` (recurs periodically) |
| fetch dies: `early EOF` / `invalid index-pack output` / `MAC incorrect` / `Bad packet length` | coding link corrupts sustained server→client flows (small ops like `ls-remote` still work) | retry once; then fetch the same commits from the gitcode mirror: `git -c http.proxy= -c https.proxy= fetch https://gitcode.com/xLLM-AI/xllm.git main --no-tags` |
| rebase replays from the root commit (`init: create xllm`) | the repo got **shallowed** — never fetch coding with `--depth=1` | reconnect: `git fetch coding main --depth=10` (server supports `--depth`, NOT `--deepen`/`--shallow-since`; full `--unshallow` dies on the link) |
| `gitcode.com` HTTPS returns HTML garbage | proxy mangling | bypass with `-c http.proxy= -c https.proxy=`; SSH to gitcode is port-443 but the key may not be registered (`Permission denied (publickey)`) |

## Push

```bash
git push --force-with-lease coding <branch>
```

- `<branch>` is whatever branch the work actually lives on (e.g.
  `zlh_offline_infer` in past sessions) — check `git branch --show-current`
  and the remote's real state instead of assuming a name.
- After any rebase the update is non-fast-forward → `--force-with-lease` is
  required (safe variant: fails if someone else moved the ref).
- A plain (non-force) push only works when the remote tip is an ancestor of
  the local tip.
- Missing commits named by the hook = payload commits (including mainline
  commits brought in by the rebase) violating the format — those cannot be
  reworded; escalate instead of rewriting mainline history.

## Submodule handling (case-by-case, not a blanket rule)

`setup.py pre_build` exits when submodule gitlinks drift from the parent
records. How to resolve depends on the **actual situation**:

- **Drift is intentional local state** (e.g. feature verified against newer
  submodule commits, not meant to be shared yet) → keep it out of commits and
  use the stage/restore workaround for builds:

  ```bash
  git add third_party/Mooncake third_party/xllm_ops   # stage gitlinks -> validator passes
  SKIP_TEST=1 python3 setup.py bdist_wheel            # build (SKIP_TEST skips UT)
  git restore --staged third_party/Mooncake third_party/xllm_ops
  ```

- **The submodule bump is part of the feature** (the code genuinely requires
  the new submodule version) → commit the gitlink update as a normal commit;
  no workaround needed.

Decide by checking what the drifted state is, whether the feature depends on
it, and what the user intends — do not assume one behavior fits all cases.

Never run `git fetch --depth=1` on coding (shallows the repo). Note: a plain
`git stash` captures gitlink drift, but `git stash push -- <path>` does not.

## End-to-end sequence (rebase → commit → push)

```bash
git stash push -m "wip"                     # capture worktree changes (incl. gitlink drift)
git fetch coding main
git rebase coding/main                      # resolve conflicts if any
git stash pop
# ... build + test (SKIP_TEST=1 wheel build), then commit:
git add <files>                             # decide case-by-case whether submodule
                                            # pointer updates belong in the commit
git commit -m "bugfix: <>=4 words description here."   # title-only, ends with period
# newline-less rebuild if the hook rejects (see above), then:
git push --force-with-lease coding <branch> # the branch the work actually lives on
```

Branch names, submodule dispositions, and file lists above are reference
examples from past sessions — always act on the repository's real state and
the user's actual intent at the time.

## PR/MR 规范（行云与 gitcode/github 三平台统一）

在行云发起 PR/MR 时（push 分支成功后），标题与描述遵循团队统一规范：

> **边界**：本规范只约束 **PR/MR 标题与描述**，提交信息仍按上方「Commit message format」执行，
> 两者互不影响。

**标题**：间接直白、用最精简准确的话描述 PR 主题，**纯英文**。

**正文三段式**（内容用中文，每段带 emoji + 英文关键字，顺序：why → what → verification）：

1. **# 🎯 改动说明**（why）：背景与原因，讲为什么需要这个改动。
2. **# 🔧 主要改动**（what）：改了什么，用 `-` 列表逐条列出。
3. **# ✅ 测试覆盖**（verification）：怎么证明改动正确，附真实命令输出。

**格式规范**：
- 三段标题用 `# 改动说明` / `# 主要改动` / `# 测试覆盖`（h1，与现有 MR 保持一致）
- 改动条目用 `-` 无序列表，每条一句话
- 测试输出用代码块（\`\`\`包裹），截取关键行
- 可用 emoji 增强可读性：🔧 改动、✅ 通过、📊 数据、⚠️ 注意
- 先起草给用户确认，再提交 PR/MR。

## coding-cli 常用命令（行云 PR/MR 操作）

工具路径：`~/bin/coding-cli`（宿主机和容器均可，`~/.bashrc` 已加 PATH）。

```bash
# 创建 MR（不需要 checkout，直接用已推送的分支）
~/bin/coding-cli mr create \
  --source-branch feat/xxx \
  --base main \
  --title "feat: xxx yyy zzz www." \
  -b "# 改动说明
...
# 主要改动
...
# 测试覆盖
..." \
  -R xLLM_AI/xllm

# 更新 MR（改标题/描述/评审人）
~/bin/coding-cli mr update <MR编号> -R xLLM_AI/xllm -t "新标题" -b "新描述"

# 查看/列出/关闭/重开
~/bin/coding-cli mr view <编号> -R xLLM_AI/xllm
~/bin/coding-cli mr list -R xLLM_AI/xllm
~/bin/coding-cli mr close <编号> -R xLLM_AI/xllm
```

注意：`-b` 是 body（不是 `--description`）；`-R` 指定仓库（不是 `-r`）。
API 调用时项目 ID 用数字（xllm = 958063），不用 URL 编码的路径。

## 容器内外用户 ID 不一致（共享挂载的权限互踩）

`<shared-mount>` 是宿主机与容器的共享挂载。**宿主机用户 UID=<your-uid>，
容器内默认 root（UID=0）**——两边写同一份 `.git/` 和 `~/.ssh/`，属主互踩是常态：

| 谁写的 | 后果 | 修复 |
| --- | --- | --- |
| 容器 root 写 `.git/` | 宿主机 `Permission denied`（如 `packed-refs`/`index` 读不了） | 容器内：`chown -R <uid>:<gid> <your-xllm-repo>/.git` |
| 宿主机 1012 写 `.git/` | 容器内 git 仍可用（root 无视权限），但 `git config --global` 读的是 `/root/.gitconfig` 而非共享目录的 | 通常无问题 |
| 容器 root 写 `~/.ssh/`（容器内 `/root/.ssh`） | `Bad owner or permissions on /root/.ssh/config` → SSH 全挂 | 容器内：`chown -R root:root /root/.ssh && chmod 700 /root/.ssh && chmod 600 /root/.ssh/id_* && chmod 644 /root/.ssh/known_hosts` |
| 宿主机操作后 `~/.ssh/known_hosts` 不可读 | coding-cli `git ls-remote` 失败 | 宿主机：`chmod 644 ~/.ssh/known_hosts && chmod 700 ~/.ssh` |

**`~/.bashrc` 已内置自动修复**（容器内新 shell 生效）：
- `/root/.ssh` 属主非 root 时自动 chown/chmod
- `xllm/.git` 被 root 写后自动 chown 回 <your-uid>

**最佳实践**：
1. **提交、推送、创建 PR 优先在容器内做**（pre-commit 钩子、SSH 密钥、coding-cli 认证都在容器内）
2. 宿主机 git 操作仅限查看（`git log`/`git diff`/`git status`）
3. 如果宿主机必须提交，用 `git commit --no-verify`（跳过 pre-commit），提交后必须 `git log --oneline -1` 确认成功（钩子失败是静默的）
4. 任何一侧操作完 git 后，在容器内跑一次 `chown -R <uid>:<gid> <your-xllm-repo>/.git` 归权

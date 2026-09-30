---
name: xingyun-reviewer
description: "监控行云（coding<internal-domain>）xllm 仓库 MR 的评审意见并自动处理：拉取评审评论、分类（改代码 / 提问 / 确认 / CI 问题 / 格式 / 无关）、修复并自测、提交推送、按讨论线程逐条专业回复，直到所有评审线程关闭。用户说 处理评审意见 / 回复 reviewer / 监控 MR 时使用，需要 MR 编号。"
---

# xingyun-reviewer (行云 MR 检视意见自动处理)

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `coding-cli` | `command -v coding-cli` | 缺失时 install.sh 从本机已有副本建软链 |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `docker` | `command -v docker` | 可选：容器内执行 git/自测时才需要 |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。


Monitor a Xingyun MR, process reviewer feedback, fix code, self-test, push, and
reply to reviewers. The loop runs until all review threads are resolved.


## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `common/user-communication` skill 的 Principles 与 Banned patterns 自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## Prerequisites

- `~/bin/coding-cli` on PATH (works in container and on host)
- SSH access to coding<internal-domain> (fix `~/.ssh` permissions if broken, see xingyun-push skill)
- xllm repo with pre-commit hooks available (container preferred)

## Core loop

```
1. poll MR notes (every 60s or on-demand)
2. for each new reviewer comment:
   a. classify: [code-fix | question | ack | ci-issue | nit | unrelated]
   b. if code-fix → implement fix → self-test → commit + push
   c. reply to the comment (professional, in the reviewer's language)
3. repeat until all threads resolved or user says stop
```

## Fetching review comments

```bash
# All notes (system + human) on an MR
~/bin/coding-cli api projects/958063/merge_requests/<MR>/notes

# Human comments only (filter system=true)
~/bin/coding-cli api projects/958063/merge_requests/<MR>/notes | \
  python3 -c "
import json,sys
for n in json.load(sys.stdin):
    if not n.get('system'):
        print(f\"[{n['created_at'][:16]}] {n['author']['username']}: {n['body']}\")"
```

**Project ID**: xllm = 958063. Always use the numeric ID in API paths.

## Replying to comments

**Reply per-thread, not batched.** Each reviewer comment gets its own reply
in its own discussion thread. Use the discussion API to reply to a specific
thread (this preserves context and notifies the right person):

```bash
# Reply to a specific discussion thread (preferred)
~/bin/coding-cli api projects/958063/merge_requests/<MR>/discussions/<thread_id>/notes \
  -X POST -F body="回复内容"

# General MR comment (only for non-thread remarks, not for review replies)
~/bin/coding-cli mr note <MR> -R xLLM_AI/xllm -m "内容"
```

**Never batch multiple thread replies into one general comment** — reviewers
can't tell which thread was addressed.

## Comment classification guide

| Type | Pattern | Action |
| --- | --- | --- |
| code-fix | "改成…", "建议…", "应该…", "这里有问题", "incorrect", "should be", "use X instead" | Implement fix, self-test, push |
| question | "?", "为什么", "what is", "how does" | Reply with explanation (no code change) |
| nit / style | "nit:", "格式", "naming", "indentation" | Fix if trivial, reply "done" |
| ci-issue | pipeline failure, lint error | Check CI log, fix root cause |
| ack / approval | "LGTM", "ok", "通过" | No action |
| unrelated | comments on other PRs or general discussion | Skip |

## Professional reply guidelines

1. **Language**: match the reviewer's language (Chinese comment → Chinese reply)
2. **Structure**: acknowledge → explain what was done → reference the commit
3. **Tone**: respectful, concise, no filler ("感谢指出，已修复，commit <sha>")
4. **Self-test results**: always include actual command output, not "已通过"
5. **You are the domain expert** — reviewer suggestions are input, not commands:
   - If the suggestion is **correct**: implement it, credit the reviewer
   - If the suggestion is **wrong or suboptimal**: push back with evidence —
     benchmark data, spec/code references, or a concrete counter-example.
     Never blindly comply just to "resolve" the thread.
   - If the suggestion is **partially right**: adopt the valid part, explain
     why the rest is not applicable, with specifics
   - If you're **uncertain**: say so explicitly, propose an experiment to
     verify, ask the reviewer for their reasoning
6. **Rational disagreement template**:

```
🤔 **有不同看法**
关于{具体问题}，我的理解有所不同：
{技术论据}
如果你指的是另一个场景，请补充说明。
```

   - Disagreement is healthy; silent compliance or stubborn refusal are both
     unprofessional. The goal is correctness, not thread resolution count.

Reply template (structured, compact, with emoji):

```
✅ **已修复**
- **改动**：{一句话描述}
- **自测**：{实际命令输出关键行}
- **提交**：{commit hash}
```

For non-fix replies (discussion / explanation):

```
💡 **说明**
{技术论据}
```

For disagreement:

```
🤔 **有不同看法**
{技术论据 / 代码证据 / 性能数据}
如果你指的是另一个场景，请补充说明。
```

Rules:
- use `✅` for fixed, `💡` for explanation, `🤔` for discussion, `⚠️` for partial
- bold the status keyword only (**not** the whole header)
- bullet points for 改动/自测/提交, not prose
- no `##` heading (it renders oversized); use bold text on the first line instead

## Fix → test → commit → push sequence (in container)

**NON-NEGOTIABLE: every fix MUST pass its self-test BEFORE committing.**
No test = no commit. If you can't test it, explain why and ask the user.

All git operations MUST happen inside the dev container (pre-commit hooks,
SSH keys, and coding-cli auth live there):

```bash
# 1. fix code
# 2. SELF-TEST (see checklist below) — must pass before proceeding
# 3. verify the test actually ran (check exit code, check output)
# 4. commit (title-only, ≥4 words, ends with period)
docker exec <container> bash -c 'cd <your-xllm-repo> && \
  git add <files> && \
  git commit -m "bugfix: describe the fix with four words minimum." && \
  git log --oneline -1'  # MUST verify commit succeeded (hooks can fail silently)

# 4. fix trailing newline for Xingyun hook (see xingyun-push skill)
# 5. push
docker exec <container> bash -c 'cd <your-xllm-repo> && \
  git push coding feat/<branch> --force-with-lease'

# 6. reply to reviewer
~/bin/coding-cli mr note <MR> -R xLLM_AI/xllm -m "回复内容"
```

**Pre-commit hook trap**: if `pre-commit` is not found, the commit silently
fails. ALWAYS check `git log --oneline -1` after committing. Use
`git commit --no-verify` as fallback if hooks are broken.

## Self-test rules (universal, learned from real failures)

**NON-NEGOTIABLE: every fix MUST pass its self-test BEFORE committing.**
No test = no commit. If you can't test it, explain why and ask the user.

### Rule 1: zero-residue

After renaming/deleting any symbol (variable, function, config key), grep the
entire scope for the old name and confirm zero hits. If the same logic exists
in multiple places (aliases, duplicated blocks), fix ALL occurrences in one
pass — never assume there is only one.

### Rule 2: functional test (not just syntax)

`bash -n` / `py_compile` proves parseability, NOT correctness. Before pushing,
run the actual command with:
- **happy path**: normal invocation produces expected output
- **edge cases**: missing args (should print usage, not `unbound variable`),
  empty/unset env vars, boundary values
- **negative test**: the old bad behavior no longer occurs

### Rule 3: clean-slate test

Test from an empty work directory, not one with stale state. Pre-existing
checkouts, cached artifacts, or leftover directories mask broken logic.
Use `rm -rf /tmp/test-<name>` + fresh invocation.

### Per-component-type minimum

| Changed file | Self-test |
| --- | --- |
| scripts/*.py | py_compile + functional run (Rules 1-3) |
| scripts/*.sh | bash -n + actual execution (Rules 1-3) |
| depends.yaml | yaml.safe_load + affected verify cmds |
| xllm/**/*.cpp | compile + run related unit tests |
| tests/** | run the specific test file |

## Monitoring (how it actually works)

**In-session background polling**: while the opencode session is active, a
background script polls the MR discussions every 30 seconds and writes new
comments to `/tmp/watch-mr<N>.log`. On **every user message** (any message,
not just PR-related), check the log file first — if new comments are found,
process them immediately (classify → fix → self-test → push → reply).

```bash
# Start monitoring (run once at the beginning of a PR processing session)
echo '#!/bin/bash
MR=<N>
LAST_TS="<last-processed-timestamp>"
while true; do
  ~/bin/coding-cli api projects/958063/merge_requests/$MR/discussions 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
for thread in d:
    for note in thread.get(\"notes\",[]):
        if not note.get(\"system\") and note[\"author\"][\"username\"] != \"<your-username>\" and note[\"created_at\"] > \"$LAST_TS\":
            print(f\"NEW [{note[\"created_at\"][:16]}] {note[\"author\"][\"username\"]} (thread={thread[\"id\"]}):\")
            print(f\"  {note[\"body\"][:400]}\")
            print()
" 2>/dev/null
  LAST_TS=$(date -u +%Y-%m-%dT%H:%M)
  sleep 30
done' > /tmp/watch-mr<N>.sh
chmod +x /tmp/watch-mr<N>.sh
setsid /tmp/watch-mr<N>.sh >> /tmp/watch-mr<N>.log 2>&1 &
```

**On every subsequent user message**: `cat /tmp/watch-mr<N>.log` → process
any NEW comments → truncate the log after processing.

**Limitations**: the polling dies when the host session ends. Between
sessions, the user still needs to trigger a check. For true 24/7 automation,
a coding<internal-domain> webhook → notification channel is needed (outside opencode).

## Edge cases

- **Scope guard**: only process MRs authored by yourself (`<your-username>`).
  Other people's MRs are NOT your business — even if you spot issues, do not
  auto-fix or reply unless explicitly asked by the user.
- **CI pipeline failures**: first determine if the failure is caused by your
  changes (compile error, test failure in your diff) or by infrastructure
  (network flake, unrelated test breakage, runner issue). If yours → fix
  proactively. If not yours → **ask the user before touching anything**.
- **Uncertainty protocol**: when a fix approach is ambiguous (multiple valid
  solutions, potential breaking change, reviewer intent unclear), **ask the
  user before proceeding**. Present the options with your recommendation.
  Do not guess and push.
- **Partial clone trap**: if git push fails with `Server does not allow
  request for unadvertised object` / `Packfile is truncated`, the repo is
  configured as a partial clone (`remote.coding.promisor=true`). Fix:
  `git config --unset remote.coding.promisor && git config --unset
  remote.coding.partialclonefilter` then retry push.
- **Reviewer suggests something already correct**: explain politely with code
  references, do not change
- **Conflicting suggestions from different reviewers**: flag to the user,
  do not pick sides automatically
- **Fix breaks existing tests**: revert, investigate, present analysis to user
- **MR has draft/WIP flag**: still process comments but note the WIP status
- **Comment on a file you didn't change**: check if it's a general review
  comment vs a diff comment (diff comments reference line numbers)

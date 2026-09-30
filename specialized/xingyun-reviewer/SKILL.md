---
name: xingyun-reviewer
description: "行云 MR 来了评审意见后的完整处理循环：拉评论（coding-cli）→ 按 改代码/提问/认可/CI问题/格式/无关 分类 →要改代码的先自测再进容器提交推送 → 按讨论线程逐条回复（给了 ✅已修复 / 💡说明 / 🤔有不同看法 三种回复模板），循环到所有线程关闭。含自测三规则（零残留、功能测试、干净环境）、会话内 30 秒后台轮询的启动脚本、以及别人的 MR 不碰、CI 不是自己引起的先问用户等边界。用户说 处理评审意见 / 回复 reviewer / 盯这个 MR 时使用，需要 MR 编号。"
---

# xingyun-reviewer（行云 MR 检视意见自动处理）

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

监控行云 MR，处理评审意见：修代码、自测、推送、回复评审人。
这个循环一直跑到所有评审线程都关闭为止。

## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `common/user-communication` skill 的「原则」与「禁止写法」自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## 前置条件

- `~/bin/coding-cli` 在 PATH 上（容器内和宿主机都能用）
- coding<internal-domain> 的 SSH 访问（`~/.ssh` 权限坏了先修，见 xingyun-push skill）
- xllm 仓库且 pre-commit 钩子可用（优先在容器里做）

## 核心循环

```
1. 轮询 MR 评论（每 60 秒，或按需）
2. 对每条新的评审意见：
   a. 分类：[code-fix | question | ack | ci-issue | nit | unrelated]
   b. 若是 code-fix → 实现修复 → 自测 → 提交 + 推送
   c. 回复该条意见（专业，用评审人所用的语言）
3. 重复，直到所有线程关闭或用户喊停
```

## 拉取评审意见

```bash
# MR 上的全部评论（系统 + 人）
~/bin/coding-cli api projects/958063/merge_requests/<MR>/notes

# 只要人写的（过滤 system=true）
~/bin/coding-cli api projects/958063/merge_requests/<MR>/notes | \
  python3 -c "
import json,sys
for n in json.load(sys.stdin):
    if not n.get('system'):
        print(f\"[{n['created_at'][:16]}] {n['author']['username']}: {n['body']}\")"
```

**项目 ID**：xllm = 958063。API 路径里一律用数字 ID。

## 回复评论

**按线程逐条回复，不要批量。** 每条评审意见在它自己的讨论线程里回复。
用 discussion API 回复指定线程（这样能保住上下文、也能通知到正确的人）：

```bash
# 回复指定讨论线程（首选）
~/bin/coding-cli api projects/958063/merge_requests/<MR>/discussions/<thread_id>/notes \
  -X POST -F body="回复内容"

# MR 通用评论（只用于非线程类留言，不用来回复评审）
~/bin/coding-cli mr note <MR> -R xLLM_AI/xllm -m "内容"
```

**绝不把多个线程的回复合成一条通用评论**——评审人分不清哪条线程被回复了。

## 评论分类指引

| 类型 | 典型特征 | 动作 |
| --- | --- | --- |
| code-fix（要改代码） | "改成…"、"建议…"、"应该…"、"这里有问题"、"incorrect"、"should be"、"use X instead" | 实现修复 → 自测 → 推送 |
| question（提问） | "?"、"为什么"、"what is"、"how does" | 解释回复（不改代码） |
| nit / style（格式） | "nit:"、"格式"、"naming"、"indentation" | 琐碎就改，回"done" |
| ci-issue（流水线） | 流水线失败、lint 报错 | 看 CI 日志，修根因 |
| ack / approval（认可） | "LGTM"、"ok"、"通过" | 无需动作 |
| unrelated（无关） | 别的 PR 的评论或一般讨论 | 跳过 |

## 专业回复准则

1. **语言**：跟评审人一致（中文评论就中文回复）。
2. **结构**：先认领 → 讲做了什么 → 引用提交。
3. **语气**：尊重、简短、不加废话（"感谢指出，已修复，commit <sha>"）。
4. **自测结果**：永远贴真实命令输出，不要只写"已通过"。
5. **你是这个领域的专家**——评审建议是输入，不是命令：
   - 建议**正确**：采纳，并在回复里 credit 评审人。
   - 建议**错误或次优**：拿证据反驳——基准数据、规范/代码引用、或具体反例。
     绝不为了"把线程关掉"就盲从。
   - 建议**部分正确**：采纳对的那部分，具体说明剩下的为什么不适用。
   - **拿不准**：明说拿不准，提出验证实验，或请评审人给出他的理由。
6. **理性异议模板**：

```
🤔 **有不同看法**
关于{具体问题}，我的理解有所不同：
{技术论据}
如果你指的是另一个场景，请补充说明。
```

   - 有分歧是好事；闷头照办和固执拒绝都不专业。目标是正确，
     不是"关闭线程的数量"。

回复模板（结构化、紧凑、带 emoji）：

```
✅ **已修复**
- **改动**：{一句话描述}
- **自测**：{实际命令输出关键行}
- **提交**：{commit hash}
```

非修复类回复（讨论 / 解释）：

```
💡 **说明**
{技术论据}
```

异议：

```
🤔 **有不同看法**
{技术论据 / 代码证据 / 性能数据}
如果你指的是另一个场景，请补充说明。
```

规则：
- 已修复用 `✅`，解释用 `💡`，讨论用 `🤔`，部分采纳用 `⚠️`。
- 只把状态词加粗（**不要**整行标题都加粗）。
- 改动/自测/提交用列表项，不要写成散文。
- 不要用 `##` 标题（渲染出来字号过大）；用第一行加粗代替。

## 修复 → 自测 → 提交 → 推送（在容器内）

**不可协商：每个修复在提交之前必须先过自测。** 没有测试就不提交。
测不了就说明原因并问用户。

所有 git 操作必须在开发容器里做（pre-commit 钩子、SSH 密钥、coding-cli 认证都在容器里）：

```bash
# 1. 改代码
# 2. 自测（见下面的清单）——必须通过才能继续
# 3. 确认测试真的跑了（看退出码、看输出）
# 4. 提交（只要标题，≥4 词，以句号结尾）
docker exec <container> bash -c 'cd <your-xllm-repo> && \
  git add <files> && \
  git commit -m "bugfix: describe the fix with four words minimum." && \
  git log --oneline -1'  # MUST verify commit succeeded (hooks can fail silently)

# 4. 按行云钩子要求修尾部换行（见 xingyun-push skill）
# 5. 推送
docker exec <container> bash -c 'cd <your-xllm-repo> && \
  git push coding feat/<branch> --force-with-lease'

# 6. 回复评审人
~/bin/coding-cli mr note <MR> -R xLLM_AI/xllm -m "回复内容"
```

**pre-commit 钩子陷阱**：找不到 `pre-commit` 时提交会静默失败。
提交后**必须**检查 `git log --oneline -1`。钩子坏了就退回
`git commit --no-verify`。

## 自测规则（通用，来自真实失败）

**不可协商：每个修复在提交之前必须先过自测。** 没有测试就不提交。
测不了就说明原因并问用户。

### 规则 1：零残留

改名/删除任何符号（变量、函数、配置键）之后，在整个作用域里 grep 旧名，
确认 0 命中。同一份逻辑如果存在于多处（别名、重复代码块），
必须**一次改完所有出现的地方**——绝不假设只有一处。

### 规则 2：功能测试（不只语法）

`bash -n` / `py_compile` 只能证明"能解析"，不能证明"正确"。
推送前要真的把命令跑一遍，覆盖：

- **正常路径**：正常调用产生预期输出
- **边界情况**：缺参数（应该打印用法，而不是 `unbound variable`）、
  空/未设置的环境变量、边界值
- **反向测试**：原来的坏行为不再出现

### 规则 3：干净环境测试

在空的工作目录里测，不要在有陈旧状态的目录里测。
已有的 checkout、缓存产物、残留目录会掩盖坏逻辑。
用 `rm -rf /tmp/test-<name>` + 全新调用。

### 各类文件的最低自测要求

| 改动的文件 | 自测 |
| --- | --- |
| scripts/*.py | py_compile + 功能跑通（规则 1-3） |
| scripts/*.sh | bash -n + 真实执行（规则 1-3） |
| depends.yaml | yaml.safe_load + 受影响的 verify 命令 |
| xllm/**/*.cpp | 编译 + 跑相关单元测试 |
| tests/** | 跑具体的那个测试文件 |

## 监控（实际怎么跑起来的）

**会话内后台轮询**：opencode 会话活着时，一个后台脚本每 30 秒拉一次 MR 讨论，
把新评论写进 `/tmp/watch-mr<N>.log`。**每收到一条用户消息**（任何消息，
不只 PR 相关的）都先看这个日志——发现新评论就立刻处理
（分类 → 修复 → 自测 → 推送 → 回复）。

```bash
# 启动监控（在一次 PR 处理会话的开头跑一次）
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

**之后每条用户消息**：`cat /tmp/watch-mr<N>.log` → 处理所有**新**评论 →
处理完清空日志。

**局限**：宿主会话一结束轮询就死了。会话之间仍需用户手动触发一次检查。
要真正的 7×24 自动化，需要 coding<internal-domain> 的 webhook → 通知通道（在 opencode 之外）。

## 边界情况

- **范围守卫**：只处理你自己（`<your-username>`）开的 MR。
  别人的 MR 不归你管——即使发现了问题，除非用户明确要求，不要自动修或回复。
- **CI 流水线失败**：先判断是你的改动引起的（你 diff 里的编译错误、测试失败）
  还是基础设施问题（网络抖动、无关测试挂了、runner 问题）。
  是你的 → 主动修；不是你的 → **先问用户再动手**。
- **不确定协议**：修复方案有歧义（多种可行解、可能引入破坏性变更、评审人意图不清）
  → **先问用户再继续**，给出选项并附上你的推荐。不要猜了就推。
- **partial clone 陷阱**：git push 报
  `Server does not allow request for unadvertised object` / `Packfile is truncated`
  说明仓库配成了 partial clone（`remote.coding.promisor=true`）。
  修法：`git config --unset remote.coding.promisor && git config --unset
  remote.coding.partialclonefilter`，然后重推。
- **评审人指出的问题本来就对/本来就正确**：礼貌解释并给代码引用，不要瞎改。
- **不同评审人的建议互相冲突**：报给用户，不要自动选边。
- **修复弄坏了现有测试**：回滚、排查、把分析结果给用户。
- **MR 带 draft/WIP 标记**：照常处理评论，但要注明它是 WIP。
- **评论落在你没改过的文件上**：先分清是通用评审意见还是 diff 行评论
  （diff 行评论带行号）。

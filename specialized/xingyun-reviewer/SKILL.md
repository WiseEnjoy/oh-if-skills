---
name: xingyun-reviewer
description: "行云 MR 评审意见处理循环：拉评论 → 按改代码/提问/认可/CI/格式/无关分类 → 要改代码的先自测再合规提交并重建串链推送 → 回复优先合并成带 discussion ID 的总览。含自测三规则（零残留、功能测试、干净环境）、✅已修复/💡说明/🤔有不同看法模板、别人的 MR 不碰与 CI 非自身引起先问用户等边界。触发词：处理评审意见、回复 reviewer、盯这个 MR。"
---

# xingyun-reviewer（行云 MR 检视意见自动处理）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `coding-cli` | `command -v coding-cli` | install.sh 探测常见安装位置建软链；都没有则 `npm i -g @jd/coding-cli` |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `docker` | `command -v docker` | 可选：容器内执行 git/自测时才需要 |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

监控行云 MR，处理评审意见：修代码、自测、推送、回复评审人。
这个循环一直跑到所有评审线程都关闭为止。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 前置条件

- `coding-cli` 可用：用 `command -v coding-cli` 判定（容器内外安装路径不同，别硬编码）；
  报 `env: node: ...` 是解释器不在当前 shell 的 PATH，不是工具缺失——详见 xingyun-push skill「coding-cli 常用命令」节
- coding<internal-domain> 的 SSH 访问（`~/.ssh` 权限坏了先修，见 xingyun-push skill）
- xllm 仓库且 pre-commit 钩子可用（优先在容器里做）

## 核心循环

```
1. 轮询 MR 评论（每 60 秒，或按需）
2. 对每轮新的评审意见：
   a. 分类：[code-fix | question | ack | ci-issue | nit | unrelated]
   b. 若是 code-fix → 实现修复 → 自测 → 提交 + 推送
   c. 合并同一 reviewer 的多条意见回复（专业，用评审人所用的语言）
3. 重复，直到所有线程关闭或用户喊停
```

## 拉取评审意见

```bash
# MR 上的全部评论（系统 + 人）
coding-cli api projects/958063/merge_requests/<MR>/notes

# 只要人写的（过滤 system=true）
coding-cli api projects/958063/merge_requests/<MR>/notes | \
  python3 -c "
import json,sys
for n in json.load(sys.stdin):
    if not n.get('system'):
        print(f\"[{n['created_at'][:16]}] {n['author']['username']}: {n['body']}\")"
```

**项目 ID**：xllm = 958063。API 路径里一律用数字 ID。

## 回复评论

**评论回复尽量合并，不要为每条 MR 级意见单独发一条通用评论。**
先按修复轮组织内容；同一个 reviewer 发了多条评论时，合并成一条回复。

回复优先级：

1. **Diff 线程能原地回复**：优先用 discussion API 回复原线程，保住行定位上下文。
2. **普通 MR 评论或平台不支持线程回复**：不要每条发一条 note；把同一 reviewer 的需要评论回复的意见合并成一条总览。
3. **确需拆分时**：按 reviewer 拆，不按意见数量拆；不同 reviewer 的意见不要混进同一条总览。

用 discussion API 回复指定线程（这样能保住上下文、也能通知到正确的人）：

```bash
# 回复指定讨论线程（首选）
coding-cli api projects/958063/merge_requests/<MR>/discussions/<thread_id>/notes \
  -X POST -F body="回复内容"

# MR 通用评论（非线程类留言，或作为普通评论回复的总览）
coding-cli mr note <MR> -R xLLM_AI/xllm -m "内容"
```

**合并总览必须逐项带 `discussion <id>` 和状态**，按意见顺序列“状态 + 改动 + 自测 + 提交”。
同一个 reviewer 的通用自测写一次，不要每项重复；项目级特例才单独写。
示例结构：

```
回复本轮评审：
1. discussion 3527825（@reviewer1）：✅ 已修复
   - 改动：...
2. discussion 3527860（@reviewer1）：💡 说明
   - 理由：...

自测：`...` → `39 passed`
提交：`e95d26b106ba...`
```

**拆分阈值**：默认一个 reviewer 只拆成一条回复；只有该 reviewer 明确要求独立跟进，
或合并后会超过一屏且难以定位时，才拆成多条。

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
5. **专业化表达**：回复用专业术语 + 实测数据，挤掉一切无关细节——调用者感知不到的内部细节（参数序、签名、字段布局、演进原因）**一个字都不写**，用"调用封装与实现 kernel 配套"级别的概括带过。评审方多半也是 agent，只做模式匹配：多写的每个名词都是给对方的猜测素材，会催生新一轮检视线程（真实教训：注释里一个参数名引出 4 条深审线程 + 3 轮反复）。
6. **你是这个领域的专家**——评审建议是输入，不是命令：
   - 建议**正确**：采纳，并在回复里 credit 评审人。
   - 建议**错误或次优**：拿证据反驳——基准数据、规范/代码引用、或具体反例。
     绝不为了"把线程关掉"就盲从。
   - 建议**部分正确**：采纳对的那部分，具体说明剩下的为什么不适用。
   - **拿不准**：明说拿不准，提出验证实验，或请评审人给出他的理由。
7. **理性异议模板**：

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

## 修复 → 自测 → 提交 → 推送（在容器内；即 xingyun-push「生命周期总纲」④ 的容器版）

**不可协商：每个修复在提交之前必须先过自测。** 没有测试就不提交。
测不了就说明原因并问用户。

所有 git 操作必须在开发容器里做（pre-commit 钩子、SSH 密钥、coding-cli 认证都在容器里）：

```bash
# 1. 改代码
# 2. 自测（见下面的清单）——必须通过才能继续
# 3. 确认测试真的跑了（看退出码、看输出）
# 4. 提交本轮修复（新提交追加，保留演进；消息按 xingyun-push
#    「提交信息格式」写合规——钩子会校验每个提交）
docker exec <container> bash -c 'cd <your-home-dir>/xllm && \
  git add <files> && \
  git commit -m "bugfix: address review comments on x." && \
  git log --oneline -1'  # MUST verify commit succeeded (hooks can fail silently)

# 5. 每个提交去尾换行重建（行云钩子拒绝正常 commit 的尾部换行，
#    整链重建脚本见 xingyun-push「尾部换行陷阱与多提交推送」；
#    reset --hard 前确认没有要保留的未提交改动）
docker exec <container> bash -c 'cd <your-home-dir>/xllm && \
  python3 /tmp/rebuild-chain.py coding/main && \
  git log --oneline -5'

# 6. 推送（重写了分支历史 → 必须 force-with-lease）
docker exec <container> bash -c 'cd <your-home-dir>/xllm && \
  git push coding feat/<branch> --force-with-lease'

# 7. 回复评审人（引用压缩后的新 sha）
coding-cli mr note <MR> -R xLLM_AI/xllm -m "回复内容"
```

**pre-commit 钩子陷阱**：找不到 `pre-commit` 时提交会静默失败。
提交后**必须**检查 `git log --oneline -1`。钩子坏了就退回
`git commit --no-verify`。

## 自测

自测纪律（零残留 / 功能测试 / 干净环境 + 各类文件的最低自测要求）是跨任务通用规则，
见 `common/safe-ops-rules`「规则 4」。**行云的附加约束**：没有通过自测的修复不许提交，
测不了就说明原因并问用户。

## 监控（会话内轮询）

会话存续期间用一个脱离进程组的后台轮询（写法见 `common/long-running-commands`），
每 30-60 秒拉一次 discussions，把新评论追加到日志；**每收到一条用户消息先看一次该日志**，
有新评论立刻走"分类 → 修复 → 自测 → 推送 → 回复"。

```bash
mkdir -p /tmp/agent
coding-cli api projects/958063/merge_requests/<MR>/discussions -o json > /tmp/agent/mr<MR>.json
```

把上面这条放进轮询循环即可；**不要**在 shell 里嵌套多层引号手写 JSON 解析脚本
（实测嵌套 `"` 极易把循环写坏）——先落盘 JSON，再用独立的 python 文件解析。

**局限**：宿主会话结束轮询即停，会话之间需用户手动触发一次检查。
要 7×24 自动化得靠平台 webhook，不在本 skill 范围内。

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

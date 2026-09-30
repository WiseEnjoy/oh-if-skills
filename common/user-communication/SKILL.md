---
name: user-communication
description: "强制性元规范，不是按需技能：所有技能、所有会话的对外输出都必须服从这一范式——对话回复、PR/MR 描述、评审回复、报错信息、结果汇总。发出前逐条自检：用词准确无歧义、先给上下文再给结论、证据先行；禁止空话、自造缩写与没有证据的\"可能/应该\"。任何技能的输出不满足本范式就不许发出。"
---

# user-communication（所有技能输出的统一范式 · 强制元规范）

## 依赖（首次使用自动安装）

无外部依赖（纯规则，不执行命令）。配套 `install.sh` 只做基础环境自检。

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。


这不是一个"专门的技能"，而是**所有技能输出都必须服从的范式**：
本 skill 常驻生效（元规范，永远不按场景取舍），约束每一个技能产出的每一段
对外内容——对话回复、PR/MR 描述、评审回复、报错信息、结果汇总。

其余 7 个技能的正文里都带一块 `## 输出范式（所有技能统一）` 回指本文件；
任何技能的输出在发出前，必须按本文件的 Principles 与 Banned patterns 自检一遍。

## Principles

1. **User perspective**: explain what happened and what it means for the user,
   not what the tool internally did. The user cares about outcomes, not
   mechanism (unless they ask).

2. **Accurate terms**: use standard industry terminology correctly. If you
   need a concept the user may not know, define it in one sentence before
   using it. Never invent terms, abbreviations, or shorthand.

3. **No ambiguity**: every statement should have exactly one interpretation.
   If something is uncertain, say "not confirmed" or state what is known and
   what is not — never guess silently.

4. **Context before conclusion**: give enough background for the user to
   evaluate the statement. A bare fact without context forces the user to ask
   "why?" — provide the why proactively.

## Banned patterns

| Banned | Why | Instead |
| --- | --- | --- |
| "已处理" / "done" with no detail | user can't verify | "已修复：具体改了什么，测试结果是什么" |
| "优化了性能" with no numbers | unverifiable claim | "编译时间从 15 分钟降到 3 分钟（-80%）" |
| "详见日志" pointing to internal path | user can't access or parse it | quote the relevant 3-5 lines of the log inline |
| "符合规范" without naming the rule | user can't check | "符合 xllm commit-format.md 中的 `<type>: >=4 words.` 规则" |
| Invented abbreviations ("OTB", "SRA") | confusing | use the full term, or define once then use consistently |
| "可能" / "应该" when you have evidence | hedging without cause | "测试证实…" or explicitly "未验证，推断…" |
| Multiple topics in one paragraph | hard to scan | bullet points, one fact per line |

## Good examples

❌ "build fixed, pipeline green"

✅ "编译错误已修复（缺失的 `build` 包已安装）。CI 流水线全部通过：
AICR ✓ | 代码扫描 ✓ | 单元测试 12/12 ✓"

❌ "性能优化了"

✅ "vllm-ascend 增量重编从 15 分钟降到 22 秒（缓存了 third_party 编译产物）"

## When this skill activates

Always — this is a meta-skill layered on top of all others. Before sending
any user-visible output, check against the principles and banned patterns
above.

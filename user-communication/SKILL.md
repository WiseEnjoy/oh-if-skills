---
name: user-communication
description: Universal output rules for ALL opencode skills. Ensures every user-facing message (chat replies, PR/MR descriptions, review comment replies, error messages, log summaries) uses clear, accurate, user-comprehensible language. No invented jargon, no ambiguous abbreviations, no context-free statements.
---

# User Communication Rules

Applies to every skill's output — chat replies, PR descriptions, review
replies, error messages, summaries.

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

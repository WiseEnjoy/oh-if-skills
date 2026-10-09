---
name: sync-after-squash-merge
description: "MR 被平台 squash 合入主干后本地分支的快速同步：绝不要 pull/merge/rebase 去重放已合入的提交（squash 后 patch-id 对不上，git 会逐提交冲突，慢到不可忍受）。正解四步：abort 清场 → fetch → 用触碰路径的净差异判定本地内容是否已在远端 → 是则 backup 分支 + git reset --hard coding/main。含『本地旧稿 vs 远端精修版』判别要点、reset 安全边界（未跟踪文件与子模块漂移不受影响）；根治靠黄金规则——本地 main 永远零提交、工作全在 feat 分支（见 xingyun-push 生命周期总纲）。触发词：合入主干后更新本地、同步主干、pull 冲突、本地和远端分叉、已合入怎么更新、rebase 太慢。"
---

# sync-after-squash-merge（squash 合入主干后的本地分支同步）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `git` | `command -v git` | 环境预装，install.sh 自检 |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。

## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、结果汇总、报错信息）必须先按
`meta/user-communication` skill 的「原则」与「禁止写法」自检后再发出：
用词准确无歧义、先上下文后结论、证据先行。

## 场景识别（对上号就走下面的快路）

- `git status` 报 `Your branch and 'coding/main' have diverged,
  and have N and M different commits each`
- 或 `git pull` / merge 卡在冲突，冲突文件恰好是本地提交系列碰过的那些（AA/UU）
- 且远端能找到这批工作的 squash 合入提交：
  `git log --oneline coding/main | grep <MR号或标题关键词>`

根因：平台把 MR squash 成**一个**提交合入主干。本地 N 个开发提交的 patch-id
与 squash 对不上，git 认为它们"还没合入"——pull 变成冲突地狱，rebase 把 N 个
旧提交逐个重放到已含最终内容的主干上，每一步都可能冲突。两条都是慢路。

## 正解（内容已全部在远端时，四条命令 10 秒）

```bash
git merge --abort 2>/dev/null; git rebase --abort 2>/dev/null  # 清掉半截操作
git fetch coding main
git branch backup/$(git branch --show-current)-$(date +%Y%m%d) HEAD  # 防手抖备份
git reset --hard coding/main
```

## 判定：本地内容是否已全部在远端（1 分钟内）

```bash
# 1) 本地多出的提交
git log --oneline HEAD ^coding/main
# 2) 这些提交碰过哪些路径（只在触碰路径上比较才有意义）
git diff --name-only $(git merge-base HEAD coding/main) HEAD
# 3) 触碰路径上的净差异
git diff --stat coding/main HEAD -- <上面的路径>
```

- 净差异**为空** → 内容已全部在远端 → 走上面四条命令，结束
- 净差异**非空** → 按下一节判新旧再决定

## 判别「本地旧稿 vs 远端精修版」

squash = 你的最终稿 + 评审修复，所以分叉时**默认远端更新**。证据（满足两条即定案）：

- 逐 hunk 看：本地多出的行只是被远端重写过的旧实现，不是新功能
- 远端带评审修复痕迹：更完善的错误处理、防御性注释、更稳的写法
- squash 提交时间晚于本地最新提交，且差值在评审周期内（小时级）

**确有本地新内容**（合入后又做的修复，远端没有）：先留 patch 再 reset，
作为**新提交**重做，绝不 rebase 旧系列：

```bash
git diff coding/main HEAD > /tmp/local-delta.patch
git reset --hard coding/main
git apply /tmp/local-delta.patch
```

## 安全边界与坑

- `git cherry` / patch-id 对 squash 合入**无效**（全部显示 `+`），别在这上面花时间
- 推送单位=单提交（xingyun-push）只在**主干没动你碰过的文件**时让 patch-id
  匹配上（`git cherry` 标 `-`、`git pull --rebase` 自动跳过）；主干动过照样失效——
  判定流程照走，reset 仍是终点
- `git reset --hard` 不动未跟踪文件、不动子模块工作区（漂移原样保留），只重置已跟踪内容
- reset 前必须建 backup 分支；丢弃的提交随时可从 backup 找回
- `git stash` 收不下"子模块内部脏"（状态里的小写 m，会报 no local changes）——
  这不影响 rebase/reset，别在这上面纠结
- 根治（黄金规则，见 xingyun-push「生命周期总纲」）：本地 `main` 永远零提交，
  一切工作在 `feat/<name>` 分支，合入后删分支；main 更新永远是两条命令
  `git fetch coding main && git reset --hard coding/main`、零冲突——
  本 skill 的判定流程只在"曾经违反黄金规则"后才需要

## 真实案例（2026-10-09，xllm 仓）

- 症状：本地 main 7 个提交（npu-deps-bundle 系列）vs coding/main 17 个；
  `git pull` merge 卡在 3 个文件冲突
- 诊断：7 个提交只碰 `.agents/skills/xllm-npu-deps-bundle/` 与
  `docker/npu_docker_depends.yaml`；净差异 3 文件 +9/-32，逐 hunk 全是本地旧稿
  （远端 #412 squash 17:45 已含全部内容 + 评审修复，本地 tip 14:47）
- 处置：merge --abort → backup 分支 → reset --hard coding/main，秒级完成
- 教训：先花 1 分钟做净差异判定再决定动不动 rebase；本 skill 就是为了消灭
  "逐提交考古 + 解 N 轮冲突"的慢路

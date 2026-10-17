---
name: pr-mr-workflow
description: "三平台（行云 coding、gitcode、github）共用的分支与 PR/MR 规范，单一权威来源：黄金规则（本地 main 永远零提交、一切工作在 feat/<name> 分支、合入后删分支）、同步主干与开分支的固定动作、推送单位=1 个压好的合规提交（fetch→收口→rebase→commit-tree→force-with-lease）、PR/MR 纯小写英文标题、🎯why/🔧what/✅verified 三段式正文与格式规范、面向读者的表达边界、起草不等于创建授权。平台特有部分见 xingyun-push（行云钩子与 coding-cli）与 gitcode-github-pr（token、连通性、跨仓库 head/base）。触发词：建 PR、提 MR、写 PR 描述、开分支、压提交、合入后清理。"
---

# pr-mr-workflow（分支与 PR/MR 统一规范）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `git` | `command -v git` | 环境预装，install.sh 自检 |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 黄金规则

**本地 `main` 永远零提交**——它只是上游默认分支的只读镜像；一切工作在 `feat/<name>` 分支上做，
合入后分支用完即删。这条成立后，squash 合入策略下没有任何环节需要现场推导；
违反之后的补救见 `sync-after-squash-merge`（但正道是别违反）。

| 环节 | 固定动作（照抄，不要发明） |
| --- | --- |
| ① 同步主干（日常 / 合入后 / 定期，无脑跑） | `git checkout main && git fetch <remote> main && git reset --hard <remote>/main` |
| ② 开新特性 | `git checkout -b feat/<name> main` |
| ③ 开发 | 随便打 WIP 提交（消息随意，推送前会压掉） |
| ④ 推送 / 建 PR | 压成 1 个合规提交再推（见下节）；标题与正文按本文件规范 |
| ⑤ 评审轮次 | 改代码 → 自测 → 重复④（每轮重压重推） |
| ⑥ 合入后 | 删远端分支 → `git branch -D feat/<name>` → 回① |

**PR 方向是唯一的平台差异**：行云在同仓库内分支做 MR；gitcode / github 是跨仓库
（`feat/<name>` 推到 fork，head=`<fork_owner>:feat/<name>`，base=上游默认分支）。
方向有歧义（多个 remote、多个同名仓）必须向用户确认，不猜。

## 推送单位 = 1 个压好的提交

变更单元是 PR 不是提交；平台 squash 合入保证主干上每个 PR 只落 1 个提交，
所以分支历史是一次性草稿，开发期随便 WIP。推送前收敛成 1 个：

```bash
git fetch <remote> main
git add -u && git commit -m "wip" || true    # 先收口才能 rebase（没改动就跳过）
git rebase <remote>/main                     # 三方合并，冲突只在这解
base=$(git merge-base HEAD <remote>/main)    # rebase 后 = 主干顶端
new=$(printf '%s' "feat: one two three four." | git commit-tree "$(git rev-parse HEAD^{tree})" -p "$base")
git reset --hard "$new" && git push --force-with-lease <remote> feat/<name>
```

- `git add -u` 只收已跟踪文件；未跟踪新文件按需显式 `git add`；子模块 gitlink 是否进提交逐案判断。
- `commit-tree` 直接喂无换行消息，顺带绕开行云钩子的尾部换行陷阱（见 `xingyun-push`）。
- `reset --hard` 前确认没有要保留的未提交改动（未跟踪文件与子模块漂移不受影响）。
- rebase 之后的更新都是非快进的 → 必须 `--force-with-lease`（别人动过该 ref 就会失败）。

## 标题

纯英文、统一小写单词，`type: 描述.`——描述至少 4 个空格分隔的词、句号结尾，直白精简，不要句首大写。
例：`bugfix: cap launch blocks for kernels.`

> **约束范围**：PR/MR 标题与描述、提交信息（commit message）、改动代码里的注释。
> 三平台的评审侧多半也是 agent，会扒所有提交面文本做模式匹配——多一个无关内部名词，
> 就会催生一轮猜测式检视线程。

## 正文三段式

1. **`## 🎯 为什么修改（why）`**：先写修改前现状（编号清单——共存的多份实现 / 多条路径，各自被谁使用），
   再写带来的问题（编号列表），最后写修改后的范围与覆盖清单（哪些场景、模型、模块被覆盖，哪些明确不覆盖）。
   版本、特性等背景要素要写具体。
2. **`## 🔧 改了什么（what）`**：按使用方视角自顶向下分组，每条以加粗小标题开头、一句话；
   清理 / 删除类改动独立成条并写明原因；涉及多仓改动时单列一条说明子模块指针前进。
3. **`## ✅ 已完成的验证（verified）`**：标题用英文过去式（verified，不用 verification）；
   按算子级 / 单元级与服务级 / 集成级分表（列：测试用例 | 结果）；每条结论必须附真实日志原文
   （代码块包裹、标注来源文件路径），无日志或截图佐证的结果不许写进描述；
   测试输出必须自解释，且不得包含本地路径、个人信息、内网地址等敏感信息。

格式规范：

- 三段标题用 `##`（h1 字号过大，不要用 `#`）；保留空行与列表版式，压缩字数不许牺牲排版。
- **面向读者的表达**：调用者感知不到的内部细节（参数序、符号签名、字段布局、版本演进过程）
  不进描述与注释，用一句概括代替（如"调用封装与实现 kernel 配套"）。
- 关联子模块 / 依赖仓的 PR 链接单列 `## 🔗 关联子模块 PR` 节。
- emoji 用于增强可读性：🔧 改动、✅ 通过、📊 数据、⚠️ 注意。
- **平台有描述长度上限时**（行云硬限 2000 字，超限报 `描述长度不能超过2000`）：不要为塞进限制压缩
  句子或版式，把放不下的整段内容（验证日志、关联 PR 明细）移到第一条评论，描述里留一行"详见评论"。

## 创建纪律

用户说"起草" = 只要草稿；对稿子的任何修改意见（包括改标题）都**不等于创建授权**；
必须等用户对最终稿明确说"可以创建 / 确认提交"才可创建 PR/MR。误创建立即关闭并说明。

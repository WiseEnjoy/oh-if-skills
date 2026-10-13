---
name: xingyun-push
description: "往行云仓 coding<internal-domain>:xLLM_AI/xllm.git 推代码的完整生命周期范式，每个环节固定命令照抄：黄金规则（本地 main 永远零提交，一切工作在 feat 分支，用完即删）→ 同步主干（fetch+reset 两条命令）→ 推送/建 MR（固定六行：fetch→收口WIP→rebase→压单提交→force-with-lease）→ 评审轮次重压重推 → 合入后删分支。含提交信息正则（类型+≥4词+句号、只要标题）、尾部换行钩子拒的 commit-tree 绕法、rebase 排障表（fetch 断流、shallow、ssh、代理）、子模块处置、UID 互踩、MR 三段式模板。触发词：推行云、rebase、同步主干、更新本地、定时拉主干、提交被钩子拒绝、coding 拉取失败、创建 MR。"
---

# 行云推送（xingyun-push）：rebase / 提交 / 推送规范

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| `coding-cli` | `command -v coding-cli` | 缺失时 install.sh 从本机已有副本建软链 |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。

这些规则全部来自 `coding<internal-domain>:xLLM_AI/xllm.git` 上真实的推送失败，
必须严格照做——平台用服务端钩子强制执行。

## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `meta/user-communication` skill 的「原则」与「禁止写法」自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## 生命周期总纲（先读这个；其余章节是它的参考手册）

**黄金规则：本地 `main` 永远零提交**——它只是 `coding/main` 的只读镜像，
一切工作都在 `feat/<name>` 分支上做，MR 合入后分支用完即删。
这条规则成立后，squash 合入策略下没有任何环节需要现场推导：

| 环节 | 固定动作（照抄，不要发明） |
| --- | --- |
| ① 同步主干（日常 / 合入后 / 定期，无脑跑） | `git checkout main && git fetch coding main && git reset --hard coding/main` |
| ② 开新特性 | `git checkout -b feat/<name> main` |
| ③ 开发 | 本地随便 WIP 提交（消息随意，推送前反正会压掉） |
| ④ 推送 / 建 MR | 固定六行（下面）；MR 标题/正文按「PR/MR 规范」+ coding-cli 章节 |
| ⑤ 评审轮次 | 改代码 → 自测 → 重复④ → 按线程回复（详见 xingyun-reviewer skill） |
| ⑥ MR 合入后 | 平台没自动删就删远端分支 → `git branch -D feat/<name>` → 回① |

**④ 的固定六行**（推送单位 = 1 个压好的合规提交，理由见「提交组织与推送单位」。
不管本地历史被造成什么样，六行永远收敛到同一个结果：1 个基于最新 main 的合规提交）：

```bash
git fetch coding main
git add -u && git commit -m "wip" || true   # 先收口才能 rebase（没改动就跳过）
git rebase coding/main                      # 三方合并，冲突只在这解（单提交最多一轮）
base=$(git merge-base HEAD coding/main)     # rebase 后 = coding/main 顶端
new=$(printf '%s' "feat: one two three four." | git commit-tree "$(git rev-parse HEAD^{tree})" -p "$base")
git reset --hard "$new" && git push --force-with-lease coding feat/<name>
```

- `git add -u` 只收**已跟踪**文件；未跟踪新文件按需显式 `git add`；
  子模块 gitlink 漂移要不要进提交逐案判断（见「子模块处理」）。
- 平台合入用 squash → 主干上每个 PR 只落 1 个提交，**由平台保证**，
  本地分支怎么组织提交都不影响主干；WIP 消息不必合规（压掉后不进推送载荷），
  最终消息必须过钩子正则（见下文）。
- 长周期分支的定期同步 = ④ 的前三行（fetch + 收口 + rebase）；
  不推送就不用压，下次推送时六行自动收编。
- 一切"分叉 / patch-id / pull 冲突"的根源都是往本地 main 提交过代码。
  违反黄金规则后的补救见 sync-after-squash-merge skill——但正道是别违反。

## 提交身份

提交前先确认（仓库本地配置，通常已设好）：

```
user.name  = <your-username>
user.email = <your-email>
```

## 提交信息格式（平台钩子强制）

行云推送钩子会校验**推送载荷里的每一个提交**，正则为：

```
^(feat|bugfix|docs|test|refactor|chore|style|revert|perf|model|build|skills): (\S+ ){3,}\S+\.$
```

规则：

1. 类型必须是 `feat|bugfix|docs|test|refactor|chore|style|revert|perf|model|build|skills`
   之一。`fix:` 会被**拒绝**——用 `bugfix:`。
2. 描述：至少 4 个以空格分隔的词，**必须以句号结尾**。
3. **只要标题，不要正文。** 多行正文会挂（钩子匹配的是整条消息，不只第一行）。
4. 句号之后不能有 `(#N)` 后缀（主线提交如 `... pool counts. (#168)` 通不过，
   也绝不要新引入这种写法）。

## 尾部换行陷阱

Git 永远存成 `"title\n"`，而钩子的正则是严格的行尾 `$` 语义，于是
**每一个正常创建的提交都会被拒**，报 `'<sha>' 中的提交信息不符合格式要求`，
哪怕标题看着完全合规（已实测：同一段文字去掉尾部换行就能过）。

绕过办法——用 `git commit-tree` 去掉尾部换行重建提交，保留 tree / parents /
author / committer：

```bash
# 按顺序把 NEW..OLD-TIP 之间的提交重写成无换行消息
prev=<new-base>            # 例如这串提交所基于的那个提交
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

推送前先在本地预检：

```python
import re, subprocess
pat = re.compile(r'^(feat|bugfix|docs|test|refactor|chore|style|revert|perf|model|build|skills): (\S+ ){3,}\S+\.$')
full = subprocess.run(['git','log','-1','--format=%B',sha],capture_output=True,text=True).stdout.rstrip('\n')
assert pat.match(full)
```

## 提交组织与推送单位（squash 语义下的行业惯例）

**原则（行业最优实践，squash 主干通用）**：

- **变更单元是 PR，不是提交**：one PR = one logical change。
- **分支历史是一次性草稿**：平台 squash 合入会把分支上所有提交压成主干上的
  1 个提交，本地怎么组织提交完全不影响主干。开发期**随便打 WIP 提交**
  （消息随意）——这正是 squash 模式的核心好处，不用维护分支历史的美观。
- "每个 PR 在主干上只落 1 个提交"由**平台的合入动作**保证，不需要、也不应该
  在本地把"单提交分支"当成教条去维护。
- 分叉/patch-id 问题的正解是黄金规则（本地 main 零提交 + 合入后删分支 +
  reset 同步，见总纲），与分支上有几个提交**无关**
  （2026-10-09 事故的根源是往本地 main 提交，不是多提交分支）。

**行云的成本差异（推送单位为什么固定为 1 个压好的提交）**：

- 行云钩子校验**推送载荷里的每一个提交**（正则 + 无换行）：推 N 个提交
  = N 次 commit-tree 重建；推 1 个 = 一次（即总纲④的六行）。
- squash 落到主干的消息由平台从分支/PR 生成（实测带 `(#N)` 后缀）——
  单提交让落库消息完全可控。
- 评审轮次两种行业做法都合法：每轮 append 修复提交（平台最后压掉）或每轮
  重压。行云上 append 同样要过钩子重建，所以**每轮重压回 1 个**最省
  （重复总纲④）；确需让评审人分步看时，推多个合规提交用上节的重建循环，
  只是更贵。

**压法**（= 总纲④的后三行。前提：工作树干净——改动先全部提交成 WIP；
未跟踪文件与子模块漂移不受 `reset --hard` 影响，但**要保留的未提交改动会丢**，
先确认；跑之前用 `git branch --show-current` 确认就在目标分支上）：

```bash
base=$(git merge-base HEAD coding/main)   # 分支基点；rebase 过即最新 main
tree=$(git rev-parse HEAD^{tree})         # 当前最终内容
new=$(printf '%s' "feat: one two three four." | git commit-tree "$tree" -p "$base")
git reset --hard "$new"                   # 分支上只剩这 1 个提交
git push --force-with-lease coding <branch>
```

要点：

- `commit-tree` 直接喂无换行消息——尾部换行陷阱一并绕开（见上节）。
- 消息必须过钩子正则：`类型: 至少 4 个词.`，只要标题。
- WIP 提交的消息**不必**合规——压掉后不进推送载荷，钩子看不到。
- 历史遗留的多提交分支要推送时，同样先压成 1 个再推；上节的多提交
  commit-tree 重建循环用于"确实要推多个提交"的场景。

## rebase 到行云 main（= 总纲④的第三行；长周期分支定期同步同此）

```bash
git fetch coding main
git rebase coding/main
```

网络/工具链的坑（全部真实遇到过）：

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| `Bad owner or permissions on /root/.ssh/config` | 属主被改回 UID <your-uid> | `chown -R root:root /root/.ssh`（会周期性复发，需重跑） |
| fetch 中断：`early EOF` / `invalid index-pack output` / `MAC incorrect` / `Bad packet length` | coding 链路会打断持续的服务端→客户端传输（`ls-remote` 这类小操作仍正常） | 重试一次；还不行就从 gitcode 镜像取同一批提交：`git -c http.proxy= -c https.proxy= fetch https://gitcode.com/xLLM-AI/xllm.git main --no-tags` |
| rebase 从根提交（`init: create xllm`）开始重放 | 仓库被 **shallow** 了——绝不要用 `--depth=1` fetch coding | 重连：`git fetch coding main --depth=10`（服务端支持 `--depth`，**不支持** `--deepen`/`--shallow-since`；整仓 `--unshallow` 会把链路跑挂） |
| `gitcode.com` HTTPS 返回 HTML 乱码 | 代理改包 | 用 `-c http.proxy= -c https.proxy=` 绕开；gitcode 的 SSH 走 443 端口，但本机密钥可能没注册（`Permission denied (publickey)`） |

## 推送

```bash
git push --force-with-lease coding <branch>
```

- `<branch>` 就是工作实际所在的分支——按总纲②统一用 `feat/<name>` 命名；
  用 `git branch --show-current` 和远端真实状态确认，别凭空假设分支名。
- 任何 rebase 之后的更新都是非快进的 → 必须 `--force-with-lease`
  （安全变体：别人动过这个 ref 就会失败）。
- 普通（非 force）推送只有在远端 tip 是本地 tip 的祖先时才成立。
- 钩子点名"缺失的提交" = 载荷里的提交（含 rebase 带进来的主线提交）不合规——
  这些不能改写，上报处理，**不要重写主线历史**。

## 子模块处理（逐案判断，不是一刀切）

`setup.py pre_build` 会在子模块 gitlink 与父仓库记录不一致时退出。
怎么解决取决于**实际情况**：

- **漂移是本地的有意状态**（例如功能是在更新的子模块提交上验证的，
  暂时还不打算共享）→ 不要把它提交进去，构建时用 stage/restore 绕过：

  ```bash
  git add third_party/Mooncake third_party/xllm_ops   # stage gitlinks -> validator passes
  SKIP_TEST=1 python3 setup.py bdist_wheel            # build (SKIP_TEST skips UT)
  git restore --staged third_party/Mooncake third_party/xllm_ops
  ```

- **子模块升级是功能的一部分**（代码确实需要新版本子模块）→ 把 gitlink 更新
  当普通提交提上去，不需要任何绕过。

判断依据：漂移的到底是什么、功能是否依赖它、用户想要什么——不要假设一种做法通吃。
绝不要对 coding 跑 `git fetch --depth=1`（会把仓库弄成 shallow）。
注意：普通 `git stash` 能收下 gitlink 漂移，`git stash push -- <path>` 收不下。

## 端到端流程（生命周期总纲④ 的 stash 变体）

与总纲④等价，差别是用 `git stash` 收口——适合子模块 gitlink 漂移想留在
工作区、不进 WIP 提交的场景：

```bash
git stash push -m "wip"                     # capture worktree changes (incl. gitlink drift)
git fetch coding main
git rebase coding/main                      # resolve conflicts if any
git stash pop
# ... 构建 + 测试（SKIP_TEST=1 打 wheel），然后提交 WIP（消息随意，推送前会压掉）：
git add <files>                             # decide case-by-case whether submodule
                                            # pointer updates belong in the commit
git commit -m "wip"
# 压成单提交（见「提交组织与推送单位」），commit-tree 无换行，钩子陷阱一并绕开：
base=$(git merge-base HEAD coding/main)
new=$(printf '%s' "bugfix: <>=4 words description here." | \
      git commit-tree "$(git rev-parse HEAD^{tree})" -p "$base")
git reset --hard "$new"
git push --force-with-lease coding <branch> # the branch the work actually lives on
```

上面的分支名、子模块处置、文件清单都只是历史会话的参考样例——
一律按仓库当时的真实状态和用户的真实意图来。

## PR/MR 规范（行云与 gitcode/github 三平台统一）

在行云发起 PR/MR 时（push 分支成功后），标题与描述遵循团队统一规范：

> **边界**：本规范只约束 **PR/MR 标题与描述**，提交信息仍按上方「提交信息格式」执行，
> 两者互不影响。

**标题**：间接直白、用最精简准确的话描述 PR 主题，**纯英文，统一用小写英文单词**
（`type: 小写描述.`，如 `bugfix: cap launch blocks for kernels.`，与本仓提交信息同风格；不要句首大写）。

**平台差异**：行云 MR 是**同仓库内不同分支**做 PR；gitcode/github 是**跨仓库**（fork → 上游），
同样走 `feat/<name>` 分支、本地 main 零提交（head=`<fork_owner>:feat/<name>`）——那套规则见 gitcode-github-pr skill，别混用。

**正文三段式**（内容用中文，每段带 emoji + 英文关键字，顺序：why → what → verified）：

1. **## 🎯 为什么修改（why）**：先写修改前现状（编号清单——共存的多份实现/多条路径，各自被谁使用），
   再写带来的问题（编号列表），最后写修改后的范围与覆盖清单（哪些场景/模型/模块被覆盖、哪些明确不覆盖）。
2. **## 🔧 改了什么（what）**：按使用方视角**自顶向下**分组（每条以加粗小标题开头），每条一句话；
   清理/删除类改动**独立成条并写明原因**；涉及多仓改动时单列一条说明子模块指针前进。
3. **## ✅ 已完成的验证（verified）**：标题用英文过去式（verified，不用 verification）；
   按**算子级/单元级**与**服务级/集成级**分表呈现（列：测试用例 | 结果）；每条结论必须附**真实日志原文**
   （代码块包裹、标注来源文件路径）——无日志或截图佐证的结果不许写进描述。

**格式规范**：
- 三段标题用 `## 🎯 为什么修改（why）` / `## 🔧 改了什么（what）` / `## ✅ 已完成的验证（verified）`（**h2**；h1 字号过大，不要用 `#`）
- 保留空行与列表版式：压缩字数不许牺牲排版，禁止把内容挤成整段一行式
- **面向读者的表达**：描述写读者能懂的语言——调用者感知不到的内部细节（参数序、符号签名、字段布局、版本演进过程等）**不进描述与注释**，用一句概括代替（如"调用封装与实现 kernel 配套"）。行云评审侧有 agent，只做模式匹配：多一个无关名词就多一轮猜测线程，浪费所有人时间
- **专业化表达**：术语准确、每条结论有实测数据支撑；挤掉一切与改动无直接关系的细节。这条同样约束**改动代码里的注释**——只写调用者需要知道的行为契约，不写实现演进的过程叙述
- 关联子模块/依赖仓的 PR 链接单独列 `## 🔗 关联子模块 PR` 节
- 测试输出用代码块（\`\`\`包裹），截取关键行
- 可用 emoji 增强可读性：🔧 改动、✅ 通过、📊 数据、⚠️ 注意

**描述长度限制（行云硬限制 2000 字）**：超限报错 `描述长度不能超过2000`。
处理：**不要为塞进 2000 字压缩句子或版式**——把放不下的整段内容（验证日志、关联 PR 明细等）移到第一条评论（\`~/bin/coding-cli mr note <编号> -m "$(cat body.md)"\`），描述里留一行"详见评论"指引。

**创建纪律**：用户说"起草"= 只要草稿；对稿子的任何修改意见（包括改标题）都**不等于创建授权**；
必须等用户对最终稿明确说"可以创建/确认提交"才可调用 `mr create`。误创建立即 `mr close` 并说明。

## coding-cli 常用命令（行云 PR/MR 操作）

工具路径：`~/bin/coding-cli`（宿主机和容器均可，`~/.bashrc` 已加 PATH）。

```bash
# 创建 MR（不需要 checkout，直接用已推送的分支）
~/bin/coding-cli mr create \
  --source-branch feat/xxx \
  --base main \
  --title "feat: xxx yyy zzz www." \
  -b "## 🎯 为什么修改（why）
...
## 🔧 改了什么（what）
...
## ✅ 怎么验证的（verification）
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

`/export/home` 是宿主机与容器的共享挂载。**宿主机用户 UID=<your-uid>（<your-username>），
容器内默认 root（UID=0）**——两边写同一份 `.git/` 和 `~/.ssh/`，属主互踩是常态：

| 谁写的 | 后果 | 修复 |
| --- | --- | --- |
| 容器 root 写 `.git/` | 宿主机 `Permission denied`（如 `packed-refs`/`index` 读不了） | 容器内：`chown -R <your-uid>:<your-uid> <your-home-dir>/xllm/.git` |
| 宿主机 <your-uid> 写 `.git/` | 容器内 git 仍可用（root 无视权限），但 `git config --global` 读的是 `/root/.gitconfig` 而非共享目录的 | 通常无问题 |
| 容器 root 写 `~/.ssh/`（容器内 `/root/.ssh`） | `Bad owner or permissions on /root/.ssh/config` → SSH 全挂 | 容器内：`chown -R root:root /root/.ssh && chmod 700 /root/.ssh && chmod 600 /root/.ssh/id_* && chmod 644 /root/.ssh/known_hosts` |
| 宿主机操作后 `~/.ssh/known_hosts` 不可读 | coding-cli `git ls-remote` 失败 | 宿主机：`chmod 644 ~/.ssh/known_hosts && chmod 700 ~/.ssh` |

**`~/.bashrc` 已内置自动修复**（容器内新 shell 生效）：
- `/root/.ssh` 属主非 root 时自动 chown/chmod
- `xllm/.git` 被 root 写后自动 chown 回 <your-uid>

**最佳实践**：
1. **提交、推送、创建 PR 优先在容器内做**（pre-commit 钩子、SSH 密钥、coding-cli 认证都在容器内）
2. 宿主机 git 操作仅限查看（`git log`/`git diff`/`git status`）
3. 如果宿主机必须提交，用 `git commit --no-verify`（跳过 pre-commit），提交后必须 `git log --oneline -1` 确认成功（钩子失败是静默的）
4. 任何一侧操作完 git 后，在容器内跑一次 `chown -R <your-uid>:<your-uid> <your-home-dir>/xllm/.git` 归权

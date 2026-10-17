---
name: xingyun-push
description: "行云仓推代码的平台特有规则：提交信息钩子正则（fix: 会被拒，必须 bugfix:；≥4 词 + 句号；只要标题不要正文）、尾部换行陷阱与 commit-tree 绕法、coding 链路 fetch/rebase 排障表、子模块 gitlink 逐案处置、coding-cli 调用方式（command -v 判定，别硬编码路径）与容器/宿主机 UID 互踩。分支生命周期与 PR 正文规范见 common/pr-mr-workflow。触发词：推行云、rebase、同步主干、提交被钩子拒绝、创建 MR。"
---

# 行云推送（xingyun-push）：rebase / 提交 / 推送规范

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| `coding-cli` | `command -v coding-cli` | install.sh 探测常见安装位置建软链；都没有则 `npm i -g @jd/coding-cli` |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

这些规则全部来自 `coding<internal-domain>:xLLM_AI/xllm.git` 上真实的推送失败，
必须严格照做——平台用服务端钩子强制执行。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 生命周期总纲

分支生命周期（main 零提交 + `feat/<name>` + 合入后删分支）、推送单位 = 1 个压好的提交、
PR/MR 标题与三段式正文，三平台共用，**先读 `common/pr-mr-workflow`**。
行云把那套流程里的 `<remote>` 换成 `coding` 即可，无需任何改写。

本文件只讲行云独有的五处，其余不重复：提交信息钩子正则、尾部换行陷阱、
coding 链路的 rebase/fetch 排障、子模块处置、coding-cli 与容器/宿主机 UID 互踩。

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

## 行云为什么把推送单位固定为 1 个提交

通用理由见 `common/pr-mr-workflow`；行云的额外成本差异有两条：

- 钩子校验**推送载荷里的每一个提交**（正则 + 无换行）：推 N 个提交 = N 次 commit-tree 重建，推 1 个只需一次。
- squash 落到主干的消息由平台生成（实测带 `(#N)` 后缀），单提交让落库内容完全可控。

评审轮次每轮重压回 1 个提交最省。确需让评审人分步看多个提交时，用下节的重建循环逐个改写，只是更贵。

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

## stash 变体（子模块漂移要留在工作区时）

通用压提交流程用 WIP 提交收口。若子模块 gitlink 漂移想留在工作区、不进提交，
把收口那一步换成 `git stash push -m "wip"` → `git fetch` → `git rebase` → `git stash pop`，
其余步骤不变。注意 `git stash` 能收下 gitlink 漂移，而 `git stash push -- <path>` 收不下。

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

## PR/MR 标题与描述

见 `common/pr-mr-workflow`（含行云 2000 字描述上限的处置）。提交信息另按本文件「提交信息格式」执行，两者互不影响。

## coding-cli 常用命令（行云 PR/MR 操作）

调用方式：命令名就写 `coding-cli`，**路径一律用 `command -v coding-cli` 判定，不要硬编码**——
容器里装在 `~/bin`，宿主机装在包管理器前缀下，写死任一个都会在另一处把"路径不对"误判成"工具缺失"。

报 `env: node: No such file or directory` 是**解释器**不在当前 shell 的 PATH 里（coding-cli 是 node 脚本），
不是工具缺失。换一个会加载用户 PATH 配置的 shell 调用（例如 `fish -c '<命令>'`），或临时把 node 所在
目录加进 PATH；在非交互 shell 里尤其常见，因为版本管理器的 PATH 设置通常只写进交互 shell 的配置。

MR 是否存在、是否已合入**只认 coding-cli/API 的返回**。`refs/merge-requests/*` 是陈旧快照
（实测滞后 20 多个编号），不得用 git ref 反推 MR 状态。

```bash
# 创建 MR（不需要 checkout，直接用已推送的分支）
coding-cli mr create \
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
coding-cli mr update <MR编号> -R xLLM_AI/xllm -t "新标题" -b "新描述"

# 查看/列出/关闭/重开
coding-cli mr view <编号> -R xLLM_AI/xllm
coding-cli mr list -R xLLM_AI/xllm
coding-cli mr close <编号> -R xLLM_AI/xllm
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

---
name: xllm-build
description: "构建 xLLM（本机或远端）前必须使用的通用流程：先确认真实仓库与工作区，处理正在占用输出二进制的 xllm 进程；有意漂移的 submodule gitlink 只在构建期间 stage 并用 trap 恢复；长构建脱离会话并保留日志。触发词：xllm build、python setup.py build、编译 xLLM、Text file busy、Submodule commit check failed。"
---

# xllm-build

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `git` | `command -v git` | 环境预装，install.sh 自检 |
| `python3` | `command -v python3` | 环境预装，install.sh 自检 |
| `setsid` | `command -v setsid` | install.sh 自动安装 util-linux |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 规则

1. **只在真实 xLLM 仓库执行**。用户指定远端或 SSH 时，命令必须落在远端仓库；
   非交互 shell 里 alias 可能不可见，先解析 alias 或使用等价 SSH 命令，绝不能
   静默退回本机 cwd。本机构建与远端构建使用同一套规则。
2. **构建前固定检查**：
   ```bash
   git status --short --branch
   pgrep -af '[x]llm'
   ```
   输出二进制被运行中的 xllm 进程占用时，先按用户已授权的范围停止该进程；
   保留服务日志，随后再构建，避免 `Text file busy`。
3. **子模块 gitlink 只做构建期绕过**。`setup.py` 因子模块指针漂移校验失败时，
   先确认这是本地有意状态；然后只 stage 对应 gitlink，构建结束无论成败都恢复：
   ```bash
   git add -- <submodule-path>
   trap 'git restore --staged -- <submodule-path>' EXIT
   python setup.py build
   ```
   不使用 path-specific stash、`git submodule update`、reset 或 checkout 改写子模块；
   不顺手 stage 产品代码。若指针升级属于功能本身，则正常提交指针，不走该绕过。
4. **长构建必须脱离会话**。预计超过 2 分钟时按 `common/long-running-commands`
   用 `setsid` 启动，输出写入稳定日志；用短调用轮询，不在一次工具调用里阻塞。
5. **结束前恢复现场并复核**。确认构建退出码与日志中的最终状态，gitlink 已从
   暂存区移除；`git status` 只允许出现构建前已有改动、未跟踪产物或明确预期的
   新增文件。产品提交不得带入子模块指针漂移和本地启动脚本。

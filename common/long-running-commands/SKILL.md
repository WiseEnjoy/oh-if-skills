---
name: long-running-commands
description: "任何可能超过 2 分钟的任务都必须用 setsid 完全脱离进程组再跑，否则会被 opencode bash 工具的 120 秒超时连进程组一起杀掉。适用：编译、测试、pip/npm 安装、模型/数据集下载、数据迁移、dev server、watch 循环。触发词：后台运行、编译、下载、安装、跑测试、nohup、detach、setsid；或任务死于 \"interrupted by user\" / \"build stopped: interrupted by user\"。"
---

# Long-running tasks must be fully detached

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `setsid` | `command -v setsid` | install.sh 自动安装 util-linux |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。


The opencode bash tool has a default 120 s timeout. When a command exceeds the
timeout, the tool terminates the **entire process group** of that call. This
applies to every kind of long task — compilation, tests, installs, downloads,
scripts — not only builds. Plain backgrounding does not survive it:

- `nohup cmd &` is NOT safe: nohup only ignores SIGHUP; the process stays in
  the same process group and is still killed on tool timeout.
- Symptom after a timed-out launch: `ninja: build stopped: interrupted by user`,
  or any task that "mysteriously" stops a couple of minutes after starting.


## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `common/user-communication` skill 的 Principles 与 Banned patterns 自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## Rule

If a task may run longer than ~2 minutes, launch it detached with `setsid`,
detach stdin, and redirect output to a log:

```bash
setsid bash -c 'cd /path/to/workdir && <command> > /tmp/opencode/<task>.log 2>&1' \
  < /dev/null > /dev/null 2>&1 &
```

Then confirm it is alive in a **separate** tool call, never the same one:

```bash
ps aux | grep -E "<command keyword>" | grep -v grep
```

Typical cases, same pattern:

```bash
# C++/python project build (xLLM example; go lives in /usr/local/go/bin)
setsid bash -c 'export PATH=/usr/local/go/bin:$PATH; cd <your-xllm-repo>; \
  python setup.py build > /tmp/opencode/xllm_build.log 2>&1' < /dev/null > /dev/null 2>&1 &

# dependency install / wheel build
setsid bash -c 'pip install -r requirements.txt > /tmp/opencode/pip_install.log 2>&1' < /dev/null > /dev/null 2>&1 &

# model / dataset / large file download
setsid bash -c 'huggingface-cli download <repo> > /tmp/opencode/hf_download.log 2>&1' < /dev/null > /dev/null 2>&1 &

# long test suite
setsid bash -c 'ctest --output-on-failure > /tmp/opencode/ctest.log 2>&1' < /dev/null > /dev/null 2>&1 &

# arbitrary long script / data migration
setsid bash -c 'python preprocess.py > /tmp/opencode/preprocess.log 2>&1' < /dev/null > /dev/null 2>&1 &
```

## Monitoring a detached task

Poll in separate short tool calls; never block on one long call:

```bash
ps -p <PID> > /dev/null && echo RUNNING || echo EXITED
tail -20 /tmp/opencode/<task>.log                                  # recent output
grep -oE "\[[0-9]+/[0-9]+\]" /tmp/opencode/xllm_build.log | tail -1 # ninja-style progress
grep -inE "error|failed" /tmp/opencode/<task>.log | head            # errors so far
```

Use `sleep <N>` inside a polling call with an explicit `timeout` parameter
slightly above the sleep duration (e.g. sleep 240, timeout 280000 ms).

## After a timed-out or suspicious launch

Do NOT blindly relaunch. First verify with `ps` whether the task is still
alive — a detached task may have survived, and relaunching can double-run
non-idempotent work (downloads, migrations, installs). If it was killed,
simply rerun the same command with the `setsid` pattern; builds and package
managers resume gracefully, so no cleanup is needed.

## When a plain foreground call is fine

If the command reliably finishes well under the timeout, run it directly and
raise the `timeout` parameter (e.g. 300000–900000 ms). Reserve the `setsid`
pattern for anything that may run many minutes or hours, or for servers/watch
loops meant to outlive the session.

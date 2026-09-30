---
name: long-running-commands
description: "Run ANY long-running task (builds, test suites, pip/npm installs, model or dataset downloads, data migrations, dev servers, watch loops) without it being killed. Use when launching a task in background, when a command exceeds ~2 minutes or the tool timeout, when a background job dies with \"interrupted by user\" / \"build stopped: interrupted by user\", or whenever nohup, &, detach, setsid, 后台运行, 编译, 下载, 安装, 跑测试 come up with the opencode bash tool."
---

# Long-running tasks must be fully detached

The opencode bash tool has a default 120 s timeout. When a command exceeds the
timeout, the tool terminates the **entire process group** of that call. This
applies to every kind of long task — compilation, tests, installs, downloads,
scripts — not only builds. Plain backgrounding does not survive it:

- `nohup cmd &` is NOT safe: nohup only ignores SIGHUP; the process stays in
  the same process group and is still killed on tool timeout.
- Symptom after a timed-out launch: `ninja: build stopped: interrupted by user`,
  or any task that "mysteriously" stops a couple of minutes after starting.

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

---
name: long-running-commands
description: "预计跑超过 2 分钟的命令（编译、测试、pip/npm 安装、模型或数据集下载、数据迁移、dev server、watch 循环）怎么启动和盯着：必须新建会话组脱离调用方进程组并把输出重定向到日志，否则 agent 的命令工具一超时会连整个进程组杀掉（典型症状 ninja: build stopped: interrupted by user）；Linux 用 setsid，macOS 没有 setsid 用 python os.setsid 兜底。含轮询纪律、真实核数判定（不许信 nproc）、永不编辑正在运行的脚本。触发词：后台运行、编译、下载、安装、跑测试、setsid。"
---

# 长任务必须完全脱离进程组（setsid）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| 新建会话组的能力 | `command -v setsid` 或 `python3 -c 'import os; os.setsid'` | Linux 用 install.sh 装 util-linux；macOS 无 setsid，用 python 兜底写法 |

**首次使用**：先跑 `bash <本skill目录>/install.sh`（幂等；`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`）。

## 为什么普通后台跑不行

agent 的命令工具都有调用超时（opencode 实测 120 秒），超时会杀掉该次调用的**整个进程组**——
编译、测试、安装、下载、脚本一律适用。`nohup cmd &` **不安全**：它只忽略 SIGHUP，
进程仍在同一进程组里。典型症状：`ninja: build stopped: interrupted by user`，
或任务"莫名其妙"在启动几分钟后停掉。

宿主机若提供"后台会话/yielded session"原语（JoyCode、Codex 等），优先用它，
本 skill 的脱离写法用于只有一次性命令工具的环境。

## 输出范式（所有技能统一）

本 skill 的一切对外输出，发出前按 `meta/user-communication` 的原则与禁止写法自检。

## 规则

任务可能跑超过约 2 分钟，就**新建会话组**启动、断开 stdin、输出重定向到日志。
`setsid` 只在 Linux（util-linux）上有，macOS 没有——所以先探，再退到 python 的 `os.setsid`：

```bash
# Linux
setsid bash -c 'cd <workdir> && <command> > /tmp/agent/<task>.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 可移植（Linux + macOS 通用，没有 setsid 时用这条）
python3 -c 'import os,subprocess,sys; os.setsid(); \
  subprocess.Popen(sys.argv[1:], stdout=open("/tmp/agent/<task>.log","w"), \
  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)' bash -lc 'cd <workdir> && <command>' &
```

日志目录先 `mkdir -p`。启动后在**另一次**工具调用里确认它活着，绝不在同一次调用里确认：

```bash
ps aux | grep -E "<command keyword>" | grep -v grep
```

同一套写法适用于构建、装依赖、模型/数据集下载、长测试套件、数据迁移——命令换掉即可。

# C++/python 项目构建（xLLM 示例；go 在 /usr/local/go/bin）
setsid bash -c 'export PATH=/usr/local/go/bin:$PATH; cd <your-xllm-repo>; \
  python setup.py build > /tmp/agent/xllm_build.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 装依赖 / 打 wheel
setsid bash -c 'pip install -r requirements.txt > /tmp/agent/pip_install.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 模型 / 数据集 / 大文件下载
setsid bash -c 'huggingface-cli download <repo> > /tmp/agent/hf_download.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 长测试套件
setsid bash -c 'ctest --output-on-failure > /tmp/agent/ctest.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 其它长脚本 / 数据迁移
setsid bash -c 'python preprocess.py > /tmp/agent/preprocess.log 2>&1' < /dev/null > /dev/null 2>&1 &
```

## 盯一个已脱离的任务

用一次次短调用轮询，绝不用一次长调用阻塞：

```bash
ps -p <PID> > /dev/null && echo RUNNING || echo EXITED
tail -20 /tmp/agent/<task>.log                                  # 最近输出
grep -oE "\[[0-9]+/[0-9]+\]" /tmp/agent/xllm_build.log | tail -1 # ninja 式进度
grep -inE "error|failed" /tmp/agent/<task>.log | head           # 到目前为止的报错
```

轮询调用里用 `sleep <N>` 时，工具的 `timeout` 参数要给得比 sleep 略大
（例如 sleep 240，timeout 给 280000 ms）。

盯守纪律：用户在等的任务，轮询间隔 ≤5 分钟、单次 sleep ≤10 分钟；
挂 25 分钟静默休眠等于无响应。长周期盯守用多次短调用，不用一次长阻塞。

## 启动前核实真实算力（构建并发不许信 nproc）

`nproc` 会尊重 `OMP_NUM_THREADS` 并报出缩水值——Ascend 环境常预置
`OMP_NUM_THREADS=12`，在 256 核机器上照样报 12。构建并发据此设置会浪费
一两个数量级算力（真实事故：默认 -j6 跑了三小时，--jobs 64 后 40 分钟
收工）。启动编译/测试前先取真实核数：

```bash
python3 -c "import os; print(len(os.sched_getaffinity(0)))"  # 真实可用核
grep -c ^processor /proc/cpuinfo                              # 无 python 时兜底
```

并发按真实核数给满；高并发（≥32）时 `export OMP_NUM_THREADS=1`，
防止 N 个编译进程各开 N×线程。

## 任务被质疑慢时的排查顺序

用户说"不可能这么慢"时，第一动作是查**利用率的分母**，不是先证明
"它在正常跑"：

```bash
ps -e -o pcpu,comm | awk '$1>50' | wc -l   # 满载进程数（对照并发数）
uptime                                     # load 对照真实核数
```

满载进程数 < 并发数、或 load 远低于真实核数 → 先查并发被谁压低了
（nproc 假象 / cgroup / 绑核 / -j 参数）。**"进程 99% CPU 且进度在走"
不等于"速度正常"**：6 个进程打满 6 个错认的核，与 64 个进程打满 256 核，
差一个数量级。

## 永不编辑正在运行的脚本

bash 按字节偏移惰性读脚本，运行中编辑同一文件会让后续解析错位（真实事故：
构建跑到 80% 时给脚本插入 10 行，出现 `[5/4]` 幻影迭代、`line N: 碎块):
No such file or directory` 报错、末尾 assembly 步骤静默丢失）。改任何脚本前先
`pgrep -f '[脚本名]'`（方括号防自匹配）确认无实例在跑；要热修就先杀任务
再改，或让在跑的实例用副本。

## 启动后超时或可疑时

**不要盲目重跑**。先用 `ps` 确认任务是否还活着——脱离的任务可能活下来了，
重跑会让非幂等的工作（下载、迁移、安装）跑两遍。如果确实被杀了，
直接用上面的 `setsid` 写法重跑同一条命令即可：构建和包管理器都能优雅续跑，
不需要清理。

## 什么时候可以直接前台跑

命令确定远在超时之内跑完，就直接跑，并把 `timeout` 参数调大
（例如 300000–900000 ms）。`setsid` 这套只留给可能跑几分钟到几小时的任务，
或者打算活过本次会话的服务、watch 循环。

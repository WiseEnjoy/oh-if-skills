---
name: long-running-commands
description: "预计跑超过 2 分钟的命令（编译、测试、pip/npm 安装、模型或数据集下载、数据迁移、dev server、watch 循环）怎么启动和盯着：必须用 setsid 完全脱离进程组并把输出重定向到日志，否则 opencode 的 bash 工具 120 秒一到会连进程组一起杀掉（典型症状 ninja: build stopped: interrupted by user）。包含启动模板、轮询进度、超时后先 ps 确认再决定是否重跑。触发词：后台运行、编译、下载、安装、跑测试、setsid。"
---

# 长任务必须完全脱离进程组（setsid）

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `setsid` | `command -v setsid` | install.sh 自动安装 util-linux |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。

## 为什么普通后台跑不行

opencode 的 bash 工具默认 120 秒超时。命令一旦超时，工具会杀掉那次调用的
**整个进程组**。这对所有长任务都成立——编译、测试、安装、下载、脚本，
不只是构建。普通后台化扛不住：

- `nohup cmd &` **不安全**：nohup 只是忽略 SIGHUP，进程仍在同一个进程组里，
  工具超时照样被杀。
- 启动后超时的典型症状：`ninja: build stopped: interrupted by user`，
  或者某个任务"莫名其妙"在启动几分钟后停掉。

## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `meta/user-communication` skill 的原则与禁止写法自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## 规则

任务可能跑超过约 2 分钟，就用 `setsid` 脱离启动、断开 stdin、输出重定向到日志：

```bash
setsid bash -c 'cd /path/to/workdir && <command> > /tmp/opencode/<task>.log 2>&1' \
  < /dev/null > /dev/null 2>&1 &
```

然后在**另一次**工具调用里确认它活着，绝不在同一次调用里确认：

```bash
ps aux | grep -E "<command keyword>" | grep -v grep
```

典型场景，同一套写法：

```bash
# C++/python 项目构建（xLLM 示例；go 在 /usr/local/go/bin）
setsid bash -c 'export PATH=/usr/local/go/bin:$PATH; cd <your-xllm-repo>; \
  python setup.py build > /tmp/opencode/xllm_build.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 装依赖 / 打 wheel
setsid bash -c 'pip install -r requirements.txt > /tmp/opencode/pip_install.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 模型 / 数据集 / 大文件下载
setsid bash -c 'huggingface-cli download <repo> > /tmp/opencode/hf_download.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 长测试套件
setsid bash -c 'ctest --output-on-failure > /tmp/opencode/ctest.log 2>&1' < /dev/null > /dev/null 2>&1 &

# 其它长脚本 / 数据迁移
setsid bash -c 'python preprocess.py > /tmp/opencode/preprocess.log 2>&1' < /dev/null > /dev/null 2>&1 &
```

## 盯一个已脱离的任务

用一次次短调用轮询，绝不用一次长调用阻塞：

```bash
ps -p <PID> > /dev/null && echo RUNNING || echo EXITED
tail -20 /tmp/opencode/<task>.log                                  # 最近输出
grep -oE "\[[0-9]+/[0-9]+\]" /tmp/opencode/xllm_build.log | tail -1 # ninja 式进度
grep -inE "error|failed" /tmp/opencode/<task>.log | head           # 到目前为止的报错
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

## 启动后超时或可疑时

**不要盲目重跑**。先用 `ps` 确认任务是否还活着——脱离的任务可能活下来了，
重跑会让非幂等的工作（下载、迁移、安装）跑两遍。如果确实被杀了，
直接用上面的 `setsid` 写法重跑同一条命令即可：构建和包管理器都能优雅续跑，
不需要清理。

## 什么时候可以直接前台跑

命令确定远在超时之内跑完，就直接跑，并把 `timeout` 参数调大
（例如 300000–900000 ms）。`setsid` 这套只留给可能跑几分钟到几小时的任务，
或者打算活过本次会话的服务、watch 循环。

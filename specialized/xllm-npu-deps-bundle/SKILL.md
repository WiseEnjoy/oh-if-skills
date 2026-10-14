---
name: xllm-npu-deps-bundle
description: "构建、重编或自测 xLLM NPU 统一依赖包（xllm-deps-*.run）时使用：编译本技能 npu_docker_depends.yaml 声明的算子 run 包与 python wheel、组装自解压 bundle、本机安装与验证；也覆盖在依赖配置中新增或更新组件。触发词：依赖包、deps bundle、打 run 包、算子包重编、build_deps_bundle。"
---

# xllm-npu-deps-bundle

Build the unified deps bundle in the current environment — everything runs on the local CANN stack.

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `git` | `command -v git` | install.sh 自动安装 |
| `python3` | `command -v python3` | install.sh 自动安装 |
| `cmake` | `command -v cmake` | install.sh 自动安装 |
| CANN 工具链 | `$ASCEND_HOME_PATH` | 无法由包管理器安装，需环境自带并 source `set_env.sh` |

首次使用前先跑 `bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。

## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、报错信息、结果汇总）必须先按
`meta/user-communication` skill 的「原则」与「禁止写法」自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## Source of truth

`npu_docker_depends.yaml` (in this skill's directory, next to `scripts/`) owns
the component list, build/install/verify
commands. The scripts in this skill are fully data-driven and
contain zero component knowledge: a depends change never requires a skill
change. Dynamic facts (chip flavor, proxy, github acceleration) come from the
environment or CLI at run time.

## Quick start

```bash
bash ~/.config/opencode/skills/specialized/xllm-npu-deps-bundle/scripts/build_deps_bundle.sh --soc ascend910_93
```

One bundle per --soc (CANN soc_version), e.g. ascend910_93.

Output: `~/xllm-deps-work/bundle/xllm-deps-{soc}-{arch}.run` (+ `.sha256`).
Install it right where you are: `bash xllm-deps-*.run` (root).

## Workflow: fix an operator, rebuild, reinstall

The bundle supports repeated installation. The normal loop when an operator
misbehaves:

1. fix the operator source (or bump its ref in the depends config)
2. `build_deps_bundle.sh --only <component> --force` (fast single-component rebuild)
3. full `build_deps_bundle.sh` (reuses the other artifacts, reassembles)
4. `bash xllm-deps-*.run` (reinstalls over the previous bundle cleanly:
   vendor dirs are overwritten, load_priority is deduplicated, and
   ASCEND_CUSTOM_OPP_PATH does not accumulate duplicates)

## What the build does (per component, in depends order)

1. fetch source at `ref` (github acceleration via `GH_INSTEAD_OF` if set)
2. clean build: CMake build dirs are always wiped -- incremental state from a
   previous parameter set leaks stale kernels into packages
3. install locally to detect the vendor directory (never hardcoded)
4. run the component's `verify` commands (+ `verify_device` when an NPU is
   attached) and an ABI probe (`ldd -r` reconciled against local symbols)
5. record metadata JSON (repo/ref/commit/file sha256) next to the artifacts

Then `make_bundle.py` assembles everything into one self-extracting run
package (operator run packages + wheels + metadata + env setup), with
private-address and host-path leak scans on the generated text.

## Notes

- pip build requirements from the depends config are NOT installed: their
  loose ranges (e.g. numpy<2) fight the pinned NPU stack; the environment is
  expected to provide python build deps
- artifacts are reused across runs unless `--force`; moving refs print a
  commit-mismatch warning -- use `--force` when freshness matters
- `--only NAME` builds one component (skips assembly); `--jobs N` sets
  compile parallelism. The default is sched_getaffinity cores / 2 -- never
  derived from nproc, which honors OMP_NUM_THREADS and can report a shrunken
  count on Ascend envs (observed: default -j6 on a 256-core host, kernel
  phase 10x slower than --jobs 64). On a big build host pass --jobs
  explicitly (e.g. --jobs 64) and export OMP_NUM_THREADS=1 so N compile
  processes do not each fork N*threads of OpenMP workers
- `supported_socs` in the depends config controls which SoC builds include a
  component for; adding a new SoC only extends that list

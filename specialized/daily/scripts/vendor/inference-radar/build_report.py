#!/usr/bin/env python3
"""Rank fetched repository updates and build a CANN-first inference radar HTML report."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

TIER_DEFINITIONS = [
    ("tier2", "外层 · General LLM Framework Context", "vLLM、SGLang、PyTorch 主线，仅保留对 LLM 推理方向有参考价值的产业实践。"),
    ("tier1", "中层 · Ascend Serving Adaptation", "vLLM Ascend、SGLang NPU、XLLM、MindSpore 与华为社区，关注新能力如何落到 Ascend serving。"),
    ("tier0", "内层 · CANN / Ascend Core", "CANN 算子、PyPTO、HCCL/HCOMM 与 torch_npu 兼容层，决定 NPU 推理正确性、性能和稳定性。"),
]
TIER_SOURCES = {
    "tier0": {"cann-ops-transformer", "cann-ops-nn", "cann-ops-math", "cann-pypto", "hccl", "hcomm", "torch_npu"},
    "tier1": {
        "vllm-ascend", "sgl-kernel-npu", "sglang-ascend-roadmap", "xllm",
        "hiascend-forum", "mindspore-discuss", "mindspore-blog", "gitcode-huawei-issues",
    },
    "tier2": {
        "vllm", "sglang", "pytorch",
        # NVIDIA/DSTA reference ecosystem: optimizations land here first and are
        # the benchmark Ascend paths are measured against.
        "tensorrt-llm", "mooncake", "lmdeploy", "llama-cpp",
    },
}
TIER_LABELS = {source: tier for tier, sources in TIER_SOURCES.items() for source in sources}
MIN_SELECTION_SCORE = 110
SOURCE_WEIGHT = {
    "cann-ops-transformer": 100,
    "cann-ops-nn": 94,
    "cann-pypto": 88,
    "hccl": 96,
    "hcomm": 92,
    "torch_npu": 100,
    "cann-ops-math": 84,
    "cann-ops-cv": 74,
    "vllm-ascend": 82,
    "sgl-kernel-npu": 80,
    "sglang-ascend-roadmap": 70,
    "xllm": 72,
    "vllm": 58,
    "sglang": 58,
    "pytorch": 54,
    "tensorrt-llm": 66,
    "mooncake": 62,
    "lmdeploy": 58,
    "llama-cpp": 54,
    "hackernews-llm-inference": 58,
    "lobsters-llm-inference": 58,
    "reddit-localllama": 54,
    "reddit-machinelearning": 52,
    "arxiv-llm-inference": 60,
    "vllm-blog": 64,
    "huggingface-blog": 58,
    "pytorch-blog": 58,
    "nvidia-developer-blog": 58,
    "jiqizhixin": 48,
    "qbitai": 46,
    "infoq-cn": 48,
    "hiascend-forum": 78,
    "mindspore-discuss": 74,
    "mindspore-blog": 76,
    "gitcode-huawei-issues": 78,
    "bytedance-github-issues": 64,
    "alibaba-github-issues": 64,
    "tencent-github-issues": 64,
    "deepseek-github-issues": 68,
    "zhipu-github-issues": 64,
}
SIGNAL_KEYWORDS = [
    ("flashattention", 32), ("flash_mla", 32), ("attention", 26), ("moe", 26),
    ("torch_npu", 26), ("npu", 18), ("mla", 24), ("mtp", 16), ("prefill", 20), ("first-token", 20),
    ("mxfp8", 30), ("mxfp4", 30), ("fp8", 28), ("w8a8", 28), ("int4", 24),
    ("int8", 22), ("quant", 26), ("matmul", 26), ("allreduce", 30), ("all_gather", 30),
    ("allgather", 30), ("reducescatter", 30), ("reduce_scatter", 30), ("alltoall", 28),
    ("communication", 22), ("overlap", 20), ("topology", 22), ("profiling", 20),
    ("precision", 26), ("精度", 26), ("性能优化", 24), ("性能", 16), ("超时", 20),
    ("mindie", 26), ("mindspeed", 22), ("mindspore", 18), ("昇腾", 24),
    ("cann", 20), ("hccl", 24), ("torch_npu", 26), ("vllm-ascend", 26), ("推理", 12),
    ("hang", 20), ("crash", 20), ("oom", 20), ("dtype", 20), ("shape", 16),
    ("空tensor", 22), ("graph", 16), ("compile", 16), ("ascend950", 20),
    ("ascend960", 20), ("fused", 22), ("kv cache", 24), ("paged", 22), ("kernel", 12), ("operator", 10), ("算子", 10),
]
NOISE_KEYWORDS = [
    ("cleancode", -24), ("clean code", -24), ("代码检视", -18), ("检视意见", -14),
    ("wip", -16), ("merge branch", -22), ("ci", -6), ("docs", -8), ("文档", -8),
    ("告警", -14), ("格式", -10), ("拼写", -12), ("simulation analysis", -10), ("test only", -8),
]
CURATED_RULES = [
    ("QuantizeAddLayerNorm", "Ascend950 上量化 + LayerNorm 融合路径出现精度回归，并附 golden 数据。对量化模型上线来说，这是必须优先确认的准确性风险。", "记录 issue 中的模型、dtype、shape、CANN/驱动版本；用同一 golden 输入复测当前环境，确认偏差是否仍存在。"),
    ("matmulreducescatter", "MatMul + ReduceScatter 的 MXFP4 非转置精度修复直接关系到分布式量化推理正确性。", "在 TP/EP 场景用转置与非转置权重各跑一次精度对比，记录误差指标和版本。"),
    ("AllGatherMMV2", "AllGather + MatMul 融合算子的 MXFP4 精度修复会影响通信与计算融合路径。", "对比启用/禁用该融合路径的精度和延迟，确认修复是否改变性能特征。"),
    ("flash_mla", "Flash MLA 入口加载修复并补充 eager/ACL graph 性能验证，说明 attention 主路径仍在快速演进。", "在固定输入下分别跑 eager 和 graph 模式，记录 TTFT、TPOT、峰值显存和失败日志。"),
    ("MXfp8", "QFA 对 MXFP8/FD 的支持扩展会直接影响新量化格式在 attention 路径上的可用性。", "确认当前 CANN/torch_npu 版本是否包含该能力；若包含，做一版 FP8 与基线 dtype 的正确性/性能 A/B。"),
    ("GroupedMatmulSwigluQuantV2", "GroupedMatmul + SwiGLU + Quant 的 torch-extension 适配是 MoE/MLP 量化推理的关键链路。", "检查该算子是否出现在你的模型 profiling top 算子中；若有，验证 torch-extension 调用和量化参数约束。"),
    ("CLOS_MAJOR/MINOR", "非对称拓扑下建链超时修复与多机 HCCL 稳定性直接相关。", "保留拓扑图和建链日志；在同类 2+6 拓扑上复测建链时间和失败率。"),
    ("DeepSeek-V4-flash", "DeepSeek W8A8 多机部署中 prefill 节点无法拉起，属于高优先级分布式推理稳定性问题。", "收集 prefill/decode 分离架构中各角色节点的启动日志、mooncake 配置、HCCL 版本和网络状态，先判断是通信、存储还是配置问题。"),
    ("localtime() re-entry", "crash-path 日志 hang 修复说明故障路径本身也可能放大故障。对线上定位尤其重要。", "确认部署版本是否包含该修复；在可控环境触发 crash-path 日志，观察是否阻塞。"),
    ("LayerNormGrad", "LayerNorm 反向对空 tensor 的支持会减少训练/图编译阶段的边界输入失败。", "构造 batch=0 或空维度输入，验证当前版本是否正常返回或报出明确错误。"),
    ("aclnnMatmulWeightNz", "Matmul 权重 NZ 路径未校验输出 dtype 一致性，可能把错误暴露成底层 ViewCopy/Cast 失败，增加定位成本。", "用相同 dtype 与故意不一致的 out dtype构造最小用例，确认新版本是否在入口给出明确错误。"),
    ("msprof 采集 MatMul", "msprof 在 MatMul 采集路径崩溃会直接阻塞算子级瓶颈定位。", "在相同 CANN/torch_npu 版本上采集一个固定 MatMul workload，记录崩溃栈、AIC 指标和复现命令。"),
    ("ReduceScatter BIRS", "ReduceScatter BIRS 与实验选项变化可能改变通信算法、显存占用或多机稳定性。", "在固定拓扑和消息大小下对比开启/关闭 BIRS 的通信耗时、峰值显存和失败率。"),
    ("InferDataType", "算子图注册的 dtype 推导策略会影响图编译时 Cast 与输出类型选择。", "为涉及转换/广播的算子构造 dtype 边界用例，比较新旧推导结果和额外 Cast 数量。"),
    ("NsaCompressAttentionVarLenScore", "变长 Attention 入口缺少 shape/零值校验，可能把用户错误放大为宿主侧崩溃。", "构造 kShape[1]==0、异常维度数和正常变长输入，确认错误类型与稳定性。"),
    ("stem_oam_prep_paged_kv", "paged KV 预处理算子适配 Ascend350，关系长上下文 serving 的平台覆盖。", "确认硬件与版本约束，用固定 page size 和序列长度验证输出正确性与耗时。"),
    ("does not has any binary", "FlashAttentionScore 报缺少 binary 通常指向算子包安装/加载与运行环境不匹配。", "收集 CANN 包、驱动、torch_npu 和环境变量版本；最小化复现后确认包布局是否完整。"),
    ("ReduceScatterV/AllGatherV", "变长 collective 自定义算子可为动态 shape 分布式推理提供更灵活的通信路径。", "对比固定与变长消息的通信耗时和正确性，同时检查图模式兼容性。"),
    ("AlltoAllvGroupedMatmul&GroupedMatmulAlltoAllv", "Grouped Matmul 与 AllToAll 融合链路新增 comm_mode，会影响 EP/MoE 通信与计算衔接。", "在 EP 场景验证不同 comm_mode 的输出、通信耗时和显存，记录推荐配置。"),
    ("AlltoAllvGroupedMatMulV2", "op_api 出参 executor 先用后判且忽略 Inner 返回值，可能掩盖真实调用失败。", "构造 executor 异常和正常返回场景，确认错误码是否可靠传递且不发生未定义行为。"),
    ("tiling 属性指针", "tiling 属性指针未判空会带来 graph 编译或运行期崩溃风险。", "针对空属性、缺省属性和合法属性分别跑最小图用例，确认错误边界清晰。"),
    ("C8-MXFP", "C8-MXFP/MXFP8 KV cache 与 QFA 后端组合会直接影响新量化 KV 的可用性。", "确认硬件/版本支持；对比 MXFP8 KV 与基线 KV 的输出误差、TTFT、TPOT 和峰值显存。"),
    ("Release requantized W4A4", "W4A4 MXFP4 activation 释放时机会影响 MoE 显存峰值和长序列稳定性。", "在固定 batch/token 数下对比修改前后的峰值显存、吞吐和 OOM 边界。"),
    ("INT8 C8 RoPE0", "RoPE0 的 INT8/FP8 支持扩展了量化模型在 A2/A3/A5 上的主路径覆盖。", "确认硬件适用性；对比量化 RoPE 与基线实现的输出误差和延迟。"),
    ("DeepSeek-V4-Pro-0813-w4a8", "W4A8 DeepSeek 部署启动失败是 Ascend serving 落地的高优先级阻塞点。", "保留镜像 tag、启动命令、NPU/CANN/HCCL 版本和完整日志，先区分参数解析、通信初始化与算子加载。"),
    ("head-256 paged FIA", "A2 head-256 paged FIA 非有限输出会直接威胁 serving 正确性。", "固定 head=256、batch 与序列长度，检查 NaN/Inf 和 logits 差异，并对比修复版本。"),
    ("fused_infer_attention_score", "自定义 fused infer attention score 可减少 kernel launch 与中间读写，是 attention 主路径优化方向。", "与原生实现对比相同输入的输出误差、kernel 数、延迟和峰值显存。"),
    ("Add DeepSeek V4.1 framework support", "DeepSeek V4.1 框架支持与 host offload 关系新模型在 Ascend serving 的可用性和显存策略。", "确认支持矩阵与依赖版本；用最小服务配置验证加载、prefill/decode 和显存行为。"),
    ("SGLANG_NPU_ARCH35_REQUANT", "arch35 block-FP8 到 MXFP8 requantization 门控可避免不适用硬件走错量化路径。", "分别在启用/关闭环境变量下验证输出误差、性能和日志提示。"),
    ("MXFP4 IPC loading", "MXFP4 权重 IPC 加载影响大模型启动时间与多进程显存共享方式。", "测量冷启动、热启动、权重加载耗时和进程间显存占用。"),
    ("bf16 MoE router and mxfp4 MoE", "bf16 router 与 MXFP4 expert 组合体现精度/性能权衡，对 MoE 量化部署有参考价值。", "对比 bf16 router 与量化 router 的输出质量、吞吐和显存，确认路由稳定性。"),
    ("mega-MoE expert path", "主线 mega-MoE expert 路径可作为 Ascend MoE 优化的算法与实现参照。", "阅读 dispatch/GEMM/通信组织方式，寻找可迁移到 NPU 的机会，不直接假设性能可迁移。"),
    ("batch invariance", "batch invariance 修复关系量化 MoE dispatch 在不同 batch 下的输出一致性。", "用相同请求不同 batch 划分验证 logits/top-k 结果是否稳定。"),
    ("pypto-pro 950平台", "PyPTO kernel 签名默认 int32 shape 在大 case 中溢出，会直接造成偏移与精度错误。", "构造超过 int32 表示范围的大偏移用例，确认新版本是否使用 int64 并保持结果正确。"),
    ("A2四机部署DeepSeek", "四机 W8A8 + mooncake prefill 节点拉不起来是典型多机推理部署风险。", "分层收集 prefill/decode 分离架构中各角色节点日志、mooncake 配置、HCCL 建链和网络状态，先确认首个失败组件。"),
    ("MoeInitRoutingV3", "MoEInitRoutingV3 支持 MXFP4 透传/量化，影响 MoE 路由与量化专家计算衔接。", "验证 routing 输出 dtype/layout 与 grouped matmul 约束，比较量化开启前后的精度与耗时。"),
    ("top_k_top_p_softmax", "融合 top-k/top-p sampling 算子可降低采样阶段 kernel 数和调度开销。", "对比融合前后的采样分布一致性、TPOT 和 CPU/NPU kernel 数。"),
]
THEME_RULES = [
    ("量化与精度", ["quant", "fp8", "mxfp", "w8a8", "int4", "int8", "precision", "精度"]),
    ("Attention / MoE", ["attention", "moe", "flash", "mla", "kv", "paged"]),
    ("通信与分布式", ["allreduce", "allgather", "reduce_scatter", "reducescatter", "alltoall", "hccl", "communication", "topology", "多机", "部署"]),
    ("正确性与稳定性", ["fix", "修复", "crash", "hang", "校验", "空tensor", "shape", "dtype", "失败", "异常", "超时"]),
    ("性能与 profiling", ["perf", "性能", "profil", "优化", "costmodel"]),
    ("编程模型与工具", ["pypto", "graph", "compile", "partition", "tiling", "ub", "extension"]),
    ("新算子与平台适配", ["新增", "支持", "迁移", "ascend950", "ascend960", "ascend350", "适配"]),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--scope", default="CANN 核心层")
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--candidate-output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.error("--date must use YYYY-MM-DD")
    if args.limit < 5 or args.limit > 80:
        parser.error("--limit must be between 5 and 80")
    return args


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


LLM_RELEVANT = re.compile(
    r"(?i)\b(?:attention|moe|matmul|quant|mxfp|fp8|w8a8|int4|int8|layernorm|rmsnorm|linear|softmax|gelu|silu|kv|paged|causal|conv1d|allreduce|all_gather|allgather|reduce_scatter|reducescatter|alltoall|all_to_all|communication|topology|scheduler|speculative|lora|vllm|sglang|cann|npu|ascend|mindspore|mindie|mindspeed|torch_npu|hccl|graph|compile|dtype|shape|tiling|profiling|latency|throughput|deepseek)\b|量化|算子|通信|多机|部署|性能|精度|显存|图模式|昇腾|推理"
)
LLM_EXCLUDED_TOKENS = [
    "backward", "grad", "training", "optimizer", "lstm", "rnn", "crop", "resize",
    "image", "vision", "detection", "nms", "deformable", "cross_entropy",
    "apply_add_sign", "erf", "localtime", "反向", "训练", "优化器", "图像", "视觉", "检测", "局部时间",
]


def llm_relevant(item: dict[str, Any]) -> bool:
    """Keep only changes that can affect LLM inference, not generic ML churn."""
    title = item.get("title", "")
    source = item.get("source_key", "")
    lower_title = title.lower()
    if any(token in lower_title for token in LLM_EXCLUDED_TOKENS):
        return False
    if source in {"cann-ops-transformer", "hccl", "hcomm", "torch_npu", "vllm", "vllm-ascend", "sglang", "sgl-kernel-npu",
                  "tensorrt-llm", "mooncake", "lmdeploy", "llama-cpp"}:
        # These repositories are LLM-inference centric; only remove explicit
        # training/CV/application noise above.
        return True
    if source in {"cann-ops-nn", "cann-ops-math"}:
        return bool(LLM_RELEVANT.search(title))
    if source == "cann-pypto":
        return bool(re.search(r"(?i)graph|compile|partition|tiling|dynamic|shape|matmul|attention|quant|custom|profiling|算子", title))
    if source == "pytorch":
        return bool(re.search(r"(?i)npu|privateuse1|custom op|compile|graph|quant|attention|moe|distributed|inference|serving", title))
    return bool(LLM_RELEVANT.search(title))


def score(item: dict[str, Any]) -> int:
    text = (item.get("title", "") + " " + " ".join(item.get("labels") or [])).lower()
    score_value = SOURCE_WEIGHT.get(item.get("source_key"), 50)
    score_value += sum(weight for keyword, weight in SIGNAL_KEYWORDS if keyword in text)
    score_value += sum(weight for keyword, weight in NOISE_KEYWORDS if keyword in text)
    if item.get("event") == "new":
        score_value += 10
    if item.get("state") == "merged":
        score_value += 14
    if item.get("type") == "pull_request":
        score_value += 8
    if re.search(r"bug|fix|修复|校验|不支持|失败|异常|精度|crash|hang|超时", text, re.I):
        score_value += 12
    if re.search(r"feat|新增|支持|迁移|适配", text, re.I):
        score_value += 10
    if any(needle.lower() in text for needle, _, _ in CURATED_RULES):
        score_value += 32
    return score_value


def tier_for(item: dict[str, Any]) -> str:
    item_tier = item.get("tier")
    if item_tier in {"tier0", "tier1", "tier2"}:
        return item_tier
    return TIER_LABELS.get(item.get("source_key", ""), "unclassified")


def theme(item: dict[str, Any]) -> str:
    text = (item.get("title", "") + " " + item.get("source_key", "")).lower()
    for name, keywords in THEME_RULES:
        if any(keyword in text for keyword in keywords):
            return name
    return "其他技术更新"


def interpretation(item: dict[str, Any]) -> tuple[str, str]:
    title = item.get("title", "")
    for needle, why, test in CURATED_RULES:
        if needle.lower() in title.lower():
            return why, test
    item_theme = theme(item)
    if item_theme == "量化与精度":
        return "量化路径的精度、约束或文档变化会直接影响模型输出正确性和可部署性。", "记录当前量化配置、dtype 和 shape；用固定 golden 输入复测误差，并对比相关算子版本。"
    if item_theme == "Attention / MoE":
        return "Attention/MoE 是推理吞吐、显存和长上下文能力的关键路径。", "在固定 batch/seq length 下记录 TTFT、TPOT、吞吐和峰值显存，判断是否值得纳入版本评估。"
    if item_theme == "通信与分布式":
        return "通信建链、collective 或多机部署变化会影响 TP/EP/PP 稳定性和扩展效率。", "保留拓扑、日志和版本信息；对比修改前后建链时间、通信耗时和失败率。"
    if item_theme == "正确性与稳定性":
        return "边界 shape、空 tensor、指针判空或异常路径修复能减少图编译和运行时崩溃。", "构造最小复现输入；确认错误是否从静默错误或崩溃变成明确报错。"
    if item_theme == "性能与 profiling":
        return "性能或 profiling 变化可能改变瓶颈判断依据。", "在固定输入下对比修改前后 top 算子耗时、总延迟和吞吐。"
    if item_theme == "编程模型与工具":
        return "PyPTO、graph/compile 或 tiling 相关变化会影响自定义算子开发效率与图执行路径。", "用一个最小自定义算子或 graph 用例验证接口约束、shape 支持和生成产物。"
    return "该更新属于平台适配或算子能力变化，可作为版本评估的候选项。", "先确认适用硬件和版本；若有相关模型路径，再做小规模正确性和性能验证。"


def merge_inputs(paths: list[Path]) -> dict[str, Any]:
    data: dict[str, Any] = {"sources": [], "items": [], "errors": [], "inputs": []}
    seen_sources = set()
    seen_items = set()
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data["inputs"].append(str(path))
        data.update(
            {
                "generated_at_utc": max(data.get("generated_at_utc", ""), raw.get("generated_at_utc", "")),
                "repository_cutoff_utc": min(data.get("repository_cutoff_utc", raw.get("repository_cutoff_utc", "9999")), raw.get("repository_cutoff_utc", "9999")),
                "repository_window_hours": max(
                    data.get("repository_window_hours", 0), raw.get("repository_window_hours", 0)
                ),
                "github_token_present": data.get("github_token_present", False)
                or bool(raw.get("github_token_present", False)),
                "gitcode_token_present": data.get("gitcode_token_present", False)
                or bool(raw.get("gitcode_token_present", False)),
                "source_policy": raw.get("source_policy", {}),
            }
        )
        for source in raw.get("sources", []):
            if source.get("key") not in seen_sources:
                seen_sources.add(source.get("key"))
                data["sources"].append(source)
        for item in raw.get("items", []):
            key = (item.get("source_key"), item.get("id") or item.get("number"), item.get("url"))
            if key not in seen_items:
                seen_items.add(key)
                data["items"].append(item)
        data["errors"].extend(raw.get("errors", []))
    return data


def title_key(item: dict[str, Any]) -> tuple[str, str]:
    text = item.get("title", "").lower()
    text = re.sub(r"\[[^]]*\]", " ", text)
    for word in ("需求建议", "缺陷反馈", "文档反馈", "商分分支", "商分", "分支", "问题", "修复", "fix", "feat", "requirement", "bug-report"):
        text = text.replace(word, " ")
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)[:70]
    return item.get("source_key", ""), normalized


def enrich(item: dict[str, Any]) -> dict[str, Any]:
    enriched = {**item, "score": score(item), "theme": theme(item), "tier": tier_for(item), "duplicate_count": 1}
    why, test = interpretation(item)
    enriched["why_it_matters"], enriched["verification"] = why, test
    return enriched


def tier_targets(limit: int) -> dict[str, int]:
    """Allocate a CANN-first, but not CANN-only, distribution."""
    tier0 = max(1, round(limit * 0.62))
    tier1 = max(1, round(limit * 0.22))
    tier2 = max(0, limit - tier0 - tier1)
    # If a very small limit rounds too aggressively, preserve at least one
    # general-framework item when the user requested at least five updates.
    if limit >= 5 and tier2 == 0:
        tier2 = 1
        tier0 = max(1, limit - tier1 - tier2)
    return {"tier0": tier0, "tier1": tier1, "tier2": tier2}


def select_tier(
    candidates: list[dict[str, Any]], tier: str, target: int
) -> list[dict[str, Any]]:
    """Select high-signal items with source and theme diversity controls."""
    pool = [
        item for item in candidates
        if item.get("tier") == tier and item.get("score", 0) >= MIN_SELECTION_SCORE
    ]
    if not pool or target <= 0:
        return []

    # Tier-specific source ceilings prevent one busy repository from crowding
    # out adjacent operator/communication/framework signals.
    source_ceiling = {"tier0": max(2, math.ceil(target * 0.45)), "tier1": max(2, math.ceil(target * 0.70)), "tier2": max(1, math.ceil(target * 0.40))}
    theme_ceiling = max(2, math.ceil(target * 0.30))
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    source_counts: Counter[str] = Counter()
    theme_counts: Counter[str] = Counter()

    def can_add(item: dict[str, Any]) -> bool:
        return (
            id(item) not in selected_ids
            and source_counts[item["source_key"]] < source_ceiling[tier]
            and theme_counts[item["theme"]] < theme_ceiling
        )

    def add(item: dict[str, Any]) -> None:
        selected.append(item)
        selected_ids.add(id(item))
        source_counts[item["source_key"]] += 1
        theme_counts[item["theme"]] += 1

    for item in pool[:3]:
        add(item)

    # For Tier 0, ensure every requested core area (operator families, PyPTO,
    # HCCL/HCOMM, torch_npu) has a representative when a qualifying item exists.
    # This prevents a very busy transformer repository from hiding adjacent risks.
    tier_sources = sorted({item["source_key"] for item in pool})
    if len(tier_sources) <= target:
        for source_key in tier_sources:
            if any(item["source_key"] == source_key for item in selected):
                continue
            representative = next(item for item in pool if item["source_key"] == source_key)
            add(representative)

    for item in pool:
        if len(selected) >= target:
            break
        if can_add(item):
            add(item)

    # Relax theme first, then source diversity, but never lower the score bar.
    if len(selected) < target:
        for item in pool:
            if len(selected) >= target:
                break
            if id(item) not in selected_ids and source_counts[item["source_key"]] < source_ceiling[tier]:
                add(item)
    if len(selected) < target:
        for item in pool:
            if len(selected) >= target:
                break
            if id(item) not in selected_ids:
                add(item)

    return sorted(selected, key=lambda item: (item["score"], item.get("timestamp", "")), reverse=True)


def select(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        (item for item in items if llm_relevant(item)),
        key=lambda item: (score(item), item.get("timestamp", "")),
        reverse=True,
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in ranked:
        key = title_key(item)
        if key in grouped:
            grouped[key]["duplicate_count"] += 1
            continue
        grouped[key] = enrich(item)
    candidates = sorted(grouped.values(), key=lambda item: (item["score"], item.get("timestamp", "")), reverse=True)
    targets = tier_targets(limit)
    selected: list[dict[str, Any]] = []
    for tier, _title, _description in TIER_DEFINITIONS:
        selected.extend(select_tier(candidates, tier, targets[tier]))
    return sorted(
        selected,
        key=lambda item: (
            next(index for index, (tier, _t, _d) in enumerate(TIER_DEFINITIONS) if tier == item["tier"]),
            -item["score"],
            item.get("timestamp", ""),
        ),
    )

def state_badge(item: dict[str, Any]) -> str:
    state = item.get("state") or "unknown"
    css = "ok" if state == "merged" else ("warn" if state == "open" else "")
    return f"<span class='badge {css}'>{e(state)}</span>"


def render_item(item: dict[str, Any]) -> str:
    duplicate = f"<span class='pill'>同题更新 ×{item['duplicate_count']}</span>" if item["duplicate_count"] > 1 else ""
    return f"""
    <article class="item">
      <div class="item-head"><span class="score">{item['score']}</span><div><h3>{e(item['title'])}</h3>
      <p class="meta">{e(item['source_name'])} · {e(item['type'])} · {e(item['event'])} · {state_badge(item)} · {e(item.get('timestamp', '')[:19].replace('T', ' '))} UTC {duplicate}</p></div></div>
      <p><a href="{e(item['url'])}" target="_blank" rel="noopener">查看原始证据</a></p>
      <dl><dt>为什么重要</dt><dd>{e(item['why_it_matters'])}</dd><dt>验证建议</dt><dd>{e(item['verification'])}</dd></dl>
    </article>"""


def render_tier_section(
    section_no: int, tier: str, title: str, description: str, items: list[dict[str, Any]]
) -> str:
    counts = Counter(item["source_key"] for item in items)
    source_text = "、".join(f"{key}（{count}）" for key, count in counts.most_common()) or "无"
    body = "".join(render_item(item) for item in items) or "<p class='meta'>本期没有达到入选门槛的重要动态；不使用低信号内容凑数。</p>"
    return f"""
<section id="{tier}"><h2>{section_no} · {e(title)}</h2><p class="meta">{e(description)}</p><p class="meta">入选：{len(items)} 条 · 来源分布：{e(source_text)}</p>{body}</section>"""


def render(args: argparse.Namespace, data: dict[str, Any], selected: list[dict[str, Any]]) -> str:
    theme_counts = Counter(item["theme"] for item in selected)
    tier_counts = Counter(item["tier"] for item in selected)
    source_counts = Counter(item["source_key"] for item in selected)
    source_status = {source.get("key"): source.get("status") for source in data.get("sources", [])}
    failed_sources = [key for key, status in source_status.items() if status in {"failed", "rate_limited", "degraded"}]
    github_sources = any(source.get("host") == "github" for source in data.get("sources", []))
    data_complete = not failed_sources and not data.get("errors")
    health = "数据完整" if data_complete else f"数据降级（{len(failed_sources)} 个源异常）"
    health_css = "ok" if data_complete else "warn"
    source_rows = []
    for source in data.get("sources", []):
        status = source.get("status", "unknown")
        css = "ok" if status == "ok" else "bad"
        errors = "; ".join(source.get("errors") or [])
        tier = TIER_LABELS.get(source.get("key", ""), "未分层")
        source_rows.append(f"<tr><td>{e(source.get('name'))}</td><td>{e(tier)}</td><td><span class='badge {css}'>{e(status)}</span></td><td>{e(source.get('item_count', 0))}</td><td>{e(errors or '—')}</td></tr>")
    theme_pills = "".join(f"<span class='pill'>{e(name)} · {count}</span>" for name, count in theme_counts.most_common())
    top_sources = "、".join(f"{key}（{count}）" for key, count in source_counts.most_common(5))
    filtered_count = sum(1 for item in data.get("items", []) if llm_relevant(item))
    summary = [
        f"本次扫描聚焦 {e(args.scope)}：原始窗口内更新 {len(data.get('items', []))} 条，LLM 推理相关性过滤后 {filtered_count} 条，最终按层级选出 {len(selected)} 条。",
        f"主次结构：Tier 0 CANN/Ascend Core {tier_counts.get('tier0', 0)} 条，Tier 1 Ascend Serving Adaptation {tier_counts.get('tier1', 0)} 条，Tier 2 General Framework Context {tier_counts.get('tier2', 0)} 条。",
        f"信号主题：{'；'.join(name for name, _ in theme_counts.most_common(3))}。主要来源：{e(top_sources)}。",
        "优先处理量化/精度、Attention/MoE、通信稳定性三类问题，因为它们分别对应输出正确性、核心吞吐和多机可部署性。",
    ]
    tier1_items = [item for item in selected if item["tier"] == "tier1"]
    actions = [
        ("建立量化精度回归清单", "把 MXFP4/MXFP8/W8A8 相关条目加入版本评估清单，固定 golden 输入、dtype、shape 和误差阈值。", selected[0]["url"] if selected else ""),
        ("复测 Attention graph/eager 差异", "选择固定 batch 与序列长度，对比 TTFT、TPOT、吞吐和峰值显存，确认新修复是否影响主路径。", next((i["url"] for i in selected if "attention" in i["title"].lower() or "mla" in i["title"].lower()), selected[0]["url"] if selected else "")),
        ("整理多机部署诊断模板", "记录拓扑、建链日志、HCCL/HCOMM 版本、prefill/decode 角色节点状态和网络指标，遇到建链或节点拉起问题先分层定位。", next((i["url"] for i in selected if i["theme"] == "通信与分布式"), "")),
        ("跟踪 Ascend serving 落地", "把 Tier 1 的新能力与 Tier 0 算子/通信约束对应起来，确认可运行版本、适用硬件和已有基准。", tier1_items[0]["url"] if tier1_items else ""),
    ]
    action_html = []
    for idx, (title, detail, url) in enumerate(actions, 1):
        link = f"<a href='{e(url)}' target='_blank' rel='noopener'>证据</a>" if url else "<span>学习行动</span>"
        action_html.append(f"<article class='action'><strong>{idx}. {e(title)}</strong><p>{e(detail)}</p><p>{link}</p></article>")
    tier_sections = []
    for index, (tier, title, description) in enumerate(TIER_DEFINITIONS, 3):
        tier_sections.append(render_tier_section(index, tier, title, description, [item for item in selected if item["tier"] == tier]))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LLM 推理优化雷达 · {e(args.date)}</title><style>
:root{{--ink:#172033;--muted:#5d6778;--line:#dfe4ec;--bg:#f6f7fb;--card:#fff;--accent:#0f766e;--warn:#b45309;--bad:#b42318;--good:#16803c;--soft:#ecfdf5}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.62 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:26px 18px 48px}} header{{background:linear-gradient(135deg,#042f2e,#0f766e);color:#fff;border-radius:18px;padding:30px;margin-bottom:18px}}
header h1{{margin:0 0 8px;font-size:clamp(24px,4vw,36px)}} header p{{margin:4px 0;color:#ccfbf1}} section{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:18px}}
h2{{margin:0 0 14px;font-size:20px}} h3{{margin:0;font-size:16px}} .badge,.pill{{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px}} .badge{{background:#e5e7eb;color:#374151}} .badge.ok{{background:#dcfce7;color:var(--good)}} .badge.warn{{background:#fef3c7;color:var(--warn)}} .badge.bad{{background:#fee2e2;color:var(--bad)}} .pill{{background:var(--soft);color:var(--accent);margin:0 6px 6px 0}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}} th{{color:var(--muted);font-size:13px}} .item,.action{{border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:12px;background:#fff}} .item-head{{display:grid;grid-template-columns:54px 1fr;gap:12px;align-items:start}} .score{{background:var(--soft);color:var(--accent);border-radius:12px;text-align:center;font-weight:700;padding:8px 0}} .meta{{color:var(--muted);font-size:13px}} dl{{margin:12px 0 0}} dt{{font-weight:700;margin-top:8px}} dd{{margin:4px 0 0}} a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} .summary li,.actions{{margin-bottom:10px}} .actions{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}} footer{{text-align:center;color:var(--muted);font-size:13px}} @media(max-width:800px){{.item-head,.actions{{display:block}}.score{{margin-bottom:8px}}.action{{margin-bottom:12px}}}}
</style></head><body><main>
<header><h1>LLM 推理优化雷达 · {e(args.date)}</h1><p>范围：{e(args.scope)} · CANN/Ascend 优先</p><p>窗口：{e(data.get('repository_window_hours'))} 小时 · 截止：{e(data.get('repository_cutoff_utc'))}</p><p>生成：{e(data.get('generated_at_utc'))} · <span class="badge {health_css}">{e(health)}</span></p></header>
<section id="data-health"><h2>1 · 数据健康</h2><table><thead><tr><th>来源</th><th>层级</th><th>状态</th><th>数量</th><th>错误</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table><p class="meta">GitHub token：{('是' if data.get('github_token_present') else '否') if github_sources else '未请求 GitHub 源'} · GitCode token：{'是' if data.get('gitcode_token_present') else '否'} · CANN 主源：GitCode，不使用 Gitee。</p></section>
<section id="executive-summary"><h2>2 · Executive Summary</h2><ul class="summary">{''.join(f'<li>{e(text)}</li>' for text in summary)}</ul><p>{theme_pills}</p></section>
{''.join(tier_sections)}
<section id="actions"><h2>6 · 今日行动</h2><div class="actions">{''.join(action_html)}</div></section>
<footer>推理优化雷达 · 证据来自公开 GitCode/GitHub API · “为什么重要/验证建议”为基于标题证据的工程判断，性能与根因需实验验证</footer>
</main></body></html>"""

def main() -> int:
    args = parse_args()
    data = merge_inputs(args.inputs)
    selected = select(data.get("items", []), args.limit)
    if args.candidate_output:
        candidate = {
            "schema_version": 1,
            "date": args.date,
            "scope": args.scope,
            "raw_update_count": len(data.get("items", [])),
            "selected_count": len(selected),
            "llm_filter_passed_count": sum(1 for item in data.get("items", []) if llm_relevant(item)),
            "tier_counts": dict(Counter(item["tier"] for item in selected)),
            "selection_policy": {
                "tier_targets": tier_targets(args.limit),
                "minimum_score": MIN_SELECTION_SCORE,
                "deduplication": "source + normalized title",
                "diversity": "per-tier source and theme ceilings",
            },
            "generated_at_utc": data.get("generated_at_utc"),
            "repository_cutoff_utc": data.get("repository_cutoff_utc"),
            "selected_items": selected,
        }
        args.candidate_output.parent.mkdir(parents=True, exist_ok=True)
        args.candidate_output.write_text(json.dumps(candidate, ensure_ascii=False, indent=None if args.compact else 2), encoding="utf-8")
    rendered = render(args, data, selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    if not args.compact:
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

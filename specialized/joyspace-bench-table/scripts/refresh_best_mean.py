#!/usr/bin/env python3
# 按 mean TTFT < SLA 重算各组合 best 与场景 best 标识。
# 用法:
#   refresh_best_mean.py                 # 兼容旧默认：5 个 p35_o15 场景，SLA=1000
#   refresh_best_mean.py rows.json       # 任务级配置，与 fill_from_bench.py 共用 rows.json
import argparse, glob, json, os, shutil, statistics

DEFAULT_SCENES = [
    ("/mnt/sfs_turbo/wise/if/Qwen3.6-35B-A3B-w8a8-mxfp8/p35_o15", 1000),
    ("/mnt/sfs_turbo/wise/if/Qwen3.6-35B-A3B/p35_o15", 1000),
    ("/mnt/sfs_turbo/wise/if/Qwen3.6-27B-FP8/p35_o15", 1000),
    ("/mnt/sfs_turbo/wise/if/Qwen3.6-27B/p35_o15", 1000),
    ("/mnt/sfs_turbo/wise/if/Qwen3-8B/p35_o15", 1000),
]

def load_scenes(path):
    if not path:
        return DEFAULT_SCENES
    cfg = json.load(open(path, encoding="utf-8"))
    scenes = []
    for row in cfg:
        scene = row["scene_dir"].rstrip("/")
        sla_ms = int(row["sla_ms"])
        if (scene, sla_ms) not in scenes:
            scenes.append((scene, sla_ms))
    return scenes

def valid_rounds(tier):
    out = []
    for rd in sorted(glob.glob(f"{tier}run-*")):
        p = f"{rd}/bench_result.json"
        if not os.path.exists(p): continue
        j = json.load(open(p))
        if j.get("completed", 0) >= j.get("num_prompts", 0) > 0:
            out.append((rd, j))
    return out

def restore_old_best(combo):
    for old in sorted(glob.glob(f"{combo}best/run-*")):
        j = json.load(open(f"{old}/bench_result.json")) if os.path.exists(f"{old}/bench_result.json") else {}
        oc = j.get("max_concurrency", 0)
        if oc <= 0:
            continue
        tier = f"{combo}runs/c{oc}"
        dest = f"{tier}/{os.path.basename(old)}"
        os.makedirs(tier, exist_ok=True)
        if os.path.exists(dest):
            trash = f"{combo}.trash/best"
            os.makedirs(trash, exist_ok=True)
            trash_dest = f"{trash}/{os.path.basename(old)}"
            if os.path.exists(trash_dest):
                continue
            shutil.move(old, trash_dest)
            continue
        shutil.move(old, dest)

def refresh_scene(scene, SLA):
    winner = None  # (tput, combo_name, c, rep_rd, rep_j)
    for combo in sorted(glob.glob(f"{scene}/v*/")):
        cn = os.path.basename(combo.rstrip("/"))
        restore_old_best(combo)
        best = None
        for tier in sorted(glob.glob(f"{combo}runs/c*/"), key=lambda p: int(p.rstrip("/").split("c")[-1])):
            c = int(tier.rstrip("/").split("c")[-1])
            rounds = valid_rounds(tier)
            if not rounds: continue
            ts = [t for _, j in rounds for t in (j.get("ttfts") or [])]
            if not ts: continue
            mean_ms = sum(ts)/len(ts)*1000
            if mean_ms >= SLA: continue
            passing = [(j["output_throughput"], rd, j) for rd, j in rounds if j["mean_ttft_ms"] < SLA]
            if not passing: continue
            tput = statistics.median([j["output_throughput"] for _, j in rounds])
            if best is None or tput > best[0]:
                rep = max(passing)
                best = (tput, c, rep[1], rep[2], mean_ms)
        if best:
            tput, c, rep_rd, rep_j, mean_ms = best
            os.makedirs(f"{combo}best", exist_ok=True)
            shutil.move(rep_rd, f"{combo}best/{os.path.basename(rep_rd)}")
            shutil.copy(f"{combo}best/{os.path.basename(rep_rd)}/bench_result.json", f"{combo}best.json")
            with open(f"{combo}/best_c.txt", "w") as f:
                f.write(f"judge=mean sla_ms={SLA}\n")
                f.write(f"best_c={c}\nbest_merged_mean_ms={mean_ms:.1f}\n")
                f.write(f"best_round_mean_ms={rep_j['mean_ttft_ms']:.2f}\n")
                f.write(f"output_throughput={rep_j['output_throughput']}\n")
            if winner is None or tput > winner[0]:
                winner = (tput, cn, c, rep_j)
        else:
            with open(f"{combo}/best_c.txt", "w") as f:
                f.write(f"judge=mean sla_ms={SLA}\nbest_c=0 (无 mean 达标档)\n")
            if os.path.exists(f"{combo}best.json"): os.remove(f"{combo}best.json")
    # 场景层
    if winner:
        tput, cn, c, rep_j = winner
        link = f"{scene}/best"
        if os.path.islink(link): os.unlink(link)
        elif os.path.exists(link): os.remove(link)
        os.symlink(cn, link)
        with open(f"{scene}/BEST.md", "w") as f:
            f.write(f"best_combo: {cn}\nbest_c: {c}\n")
            f.write(f"mean_ttft_ms: {rep_j['mean_ttft_ms']:.2f}\n")
            f.write(f"output_throughput_tok_s: {round(tput,1)}\n")
            f.write(f"judge: mean < {SLA}ms\n")
    print(scene.split("/if/")[1], "→", winner[1] + " c" + str(winner[2]) if winner else "无合格")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rows", nargs="?", help="rows.json；与 fill_from_bench.py 共用同一份配置")
    args = parser.parse_args()
    for scene, sla_ms in load_scenes(args.rows):
        refresh_scene(scene, sla_ms)
    print("DONE")

if __name__ == "__main__":
    main()

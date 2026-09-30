---
name: safe-ops-rules
description: Universal safety rules for ALL tasks. Use BEFORE any destructive or costly operation — deleting/cleaning/overwriting files (rm -rf, clean, wipe), killing processes (pkill, killall), re-running expensive jobs after a failure, or reverting changes. Trigger keywords: 删除, 清理, rm -rf, git ls-files, pkill, 增量, 重跑, 回滚.
---

# Safe Operations Rules (universal, non-negotiable)

Three hard rules distilled from a real incident (2026-09-24: deleted a
git-tracked patch file that lived inside a directory named `build/`, broke a
30-min build, then wasted more full rebuilds verifying the fix). These apply
to EVERY task — not just builds. MUST rules, never suggestions.

## Rule 1 — Destructive file ops: verify with git FIRST

Before ANY delete / clean / overwrite / revert of files or directories
(`rm -rf`, wipes, "cleanup", restoring stale state) inside any git repo:

```bash
# Run INSIDE the repo, and INSIDE each affected submodule — a submodule's
# tracked files are invisible to the parent repo's ls-files:
git ls-files -- <path>          # non-empty output => TRACKED SOURCE, do NOT delete
git status --short -- <path>    # only '??' entries => genuinely untracked, safe to remove
```

- **Tracked files are source code regardless of naming or location.** A
  directory named `build/` may contain checked-in sources (real case:
  `third_party/xllm_ops/cmake/third_party/build/modules/patch/*.patch`,
  consumed by the build; deleting it failed everything downstream).
- Only `??` untracked paths may be removed. To revert tracked files use
  `git restore <path>`, never `rm` + hope.
- Respect the project's designated output/cleanup list if one exists; do NOT
  invent extra cleanup targets from name heuristics.

## Rule 2 — Cheap verification FIRST, expensive runs LAST

After any failure, fix the root cause, then:

1. Re-verify with the cheapest mode that exercises the failing step
   (incremental build, single test, one module — not the full pipeline).
2. Only after it passes (通关), run the expensive full/clean run ONCE as
   end-to-end proof.

Never re-launch expensive full runs (clean builds, full test suites) just to
"check" a fix — iterate cheap, prove once.

## Rule 3 — pkill/pgrep self-match trap

`pkill -f "setup.py"` matches the invoking shell's own command line (the
pattern text is in it) — it kills its own shell and any wrapping
`docker exec` hangs with no output.

- Always bracket the pattern: `pkill -f "[s]etup\.py"`, `pkill -f "[b]isheng"`.
- Never place a plain `PATTERN` string in the same command line as
  `pkill -f PATTERN`.
- Confirm before/after with `pgrep -af` (bracketed); when working through
  `docker exec`, verify the container is still alive (`docker ps`).

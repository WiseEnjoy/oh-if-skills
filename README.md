# oh-if-skills

Agent skills for Codex, Claude Code, JoyCode and OpenCode — reusable workflows
distilled from real production experience, each with the failure cases that
shaped it.

## Install

```bash
git clone https://github.com/WiseEnjoy/oh-if-skills.git ~/git/oh-if-skills
bash ~/git/oh-if-skills/install-links.sh
```

`install-links.sh` symlinks this clone into each agent's skills directory, so
every agent reads the same working copy and a `git pull` takes effect
everywhere on the next session. It is idempotent — **re-run it after adding or
removing a skill**, and it will also prune links whose target is gone.

Two link shapes, because the agents differ in how they discover skills:

| Agent | Skills directory | Link shape | New skill in this repo |
| --- | --- | --- | --- |
| Codex / JoyCode / OpenCode | `<skills-dir>/<category>` | per category | visible automatically |
| Claude Code | `~/.claude/skills/<name>` | per skill | **invisible until linked** |

Claude Code only discovers `<name>/SKILL.md` one level deep, so a category
symlink does not work there (verified 2026-11-11: a flat probe appeared in the
skill list immediately, a nested one never did).

Each skill also ships an idempotent `install.sh` for its own dependencies — run
it once before first use; it exits immediately when nothing is missing.

## Skills

### meta/ — always in effect, not on-demand

| Name | What it does |
| --- | --- |
| [user-communication](meta/user-communication/) | The rules every outward message must pass: chat replies, PR/MR bodies, review replies, errors, summaries |
| [self-evolution](meta/self-evolution/) | How skills are created, maintained and rewritten: no repeated mistakes, general rules over volatile details, stay lean |

### common/ — disciplines that apply to any task

| Name | What it does |
| --- | --- |
| [safe-ops-rules](common/safe-ops-rules/) | Checks before destructive operations (`rm`, `kill`, revert, re-run) and the self-test bar before committing |
| [long-running-commands](common/long-running-commands/) | Start builds, tests and downloads detached so a tool timeout cannot kill the process group |
| [pr-mr-workflow](common/pr-mr-workflow/) | Single source of truth for branch lifecycle and PR/MR conventions across all three platforms |
| [xllm-build](common/xllm-build/) | Build xLLM safely: busy binaries, intentional submodule drift, detached builds, state restoration |

### specialized/ — bound to one platform or tool

| Name | What it does |
| --- | --- |
| [gitcode-github-pr](specialized/gitcode-github-pr/) | Create, list, view and merge pull requests on gitcode.com and github.com |
| [xingyun-push](specialized/xingyun-push/) | Push and rebase against Xingyun internal repos, including the commit-message hook rules |
| [xingyun-reviewer](specialized/xingyun-reviewer/) | Work through MR review comments: classify, fix, self-test, reply |
| [sync-after-squash-merge](specialized/sync-after-squash-merge/) | Re-sync a local branch after its MR was squash-merged (never pull/rebase/replay) |
| [ssh-password-transfer](specialized/ssh-password-transfer/) | Copy files to or from a remote host that only allows password auth |
| [opencode-skills-sync](specialized/opencode-skills-sync/) | Maintain and publish this repo: install model, skill contract, frontmatter validator, sanitization |
| [xllm-npu-deps-bundle](specialized/xllm-npu-deps-bundle/) | Build and verify the unified xLLM NPU dependency bundle (`xllm-deps-*.run`) |
| [joyspace-sheet-write](specialized/joyspace-sheet-write/) | Batch-write cells into a JoySpace (WPS-embedded) sheet, with verify-retry against dropped writes |
| [joyspace-sheet-image](specialized/joyspace-sheet-image/) | Insert a rendered PNG into a JoySpace sheet cell (lands as a `DISPIMG` formula) |
| [joyspace-bench-table](specialized/joyspace-bench-table/) | Fill a JoySpace sheet with raw vbench results — mechanical, zero manual transcription |
| [daily](specialized/daily/) | Generate the two nightly LLM inference HTML reports under a 10-minute budget |

## Layout and skill contract

A skill is a directory with a `SKILL.md` that teaches the agent one task. Skills
load on demand when the task matches their `description`; the two `meta/` skills
are always in effect.

```
<category>/<name>/
  SKILL.md      # YAML frontmatter (name, description) + the workflow
  install.sh    # idempotent dependency installer, run on first use
  scripts/      # optional helpers the skill calls
```

Every skill must satisfy all four:

1. **`name` equals the directory basename**, `[a-z0-9-]`, ≤64 chars.
2. **`description` is one double-quoted scalar**, ≤1024 chars, saying when the
   skill triggers. Quoting is not cosmetic: an unquoted value containing `: `
   makes GitHub report `mapping values are not allowed here`.
3. **Dependency section** `## 依赖（首次使用自动安装）` right after the title, with a
   `| 依赖 | 检查 | 缺失时 |` table, plus an `install.sh` that exists and is idempotent.
4. **Output-paradigm block** `## 输出范式（所有技能统一）` pointing back to
   `meta/user-communication` (every skill except that one).

Validator script: see section 2 of
[opencode-skills-sync](specialized/opencode-skills-sync/).

## Contributing

PRs welcome. Beyond the four contract items:

- Write the trigger phrases into `description` — that is what makes the skill fire.
- Document the real failure cases and how to recover, not just the happy path.
- Mark environment-specific findings as such (which machine, which date); never
  state them as universal truths.
- No credentials, internal IPs or personal paths — see the sanitization table in
  [opencode-skills-sync](specialized/opencode-skills-sync/).

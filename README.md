# oh-if-skills

OpenCode / Claude Code agent skills collection — reusable workflows distilled
from real production experience.

## Skills

Two-level layout: `skills/<category>/<name>/SKILL.md`. OpenCode discovers
nested directories recursively, so copy the category folder too.

### meta/ — meta-paradigms (always in effect, not on-demand)

| Name | Description |
| --- | --- |
| [user-communication](meta/user-communication/) | **Meta-paradigm, not an optional skill**: every skill's outward output must satisfy it — chat replies, PR/MR bodies, review replies, error messages, summaries |
| [self-evolution](meta/self-evolution/) | Three iron rules + a stability-period red line governing how every skill is created, used, maintained, and rewritten: no repeated mistakes, generalize instead of patching details, keep skills lean, rewrite instead of endless patching |

### common/ — shared disciplines (apply to every task)

| Name | Description |
| --- | --- |
| [safe-ops-rules](common/safe-ops-rules/) | Safety checks before destructive operations (rm, kill, revert, re-run) |
| [long-running-commands](common/long-running-commands/) | Run long tasks (builds, tests, downloads) detached with `setsid`, without timeout kills |
| [pr-mr-workflow](common/pr-mr-workflow/) | **Single source of truth** for branch lifecycle and PR/MR conventions shared by all three platforms: golden rule (zero commits on local main), one squashed compliant commit per push, lowercase title, three-section body |
| [xllm-build](common/xllm-build/) | Build xLLM safely in the real repository, handling busy binaries, intentional submodule drift, detached builds, and state restoration |

### specialized/ — platform-specific workflows

| Name | Description |
| --- | --- |
| [gitcode-github-pr](specialized/gitcode-github-pr/) | Create, list, view and merge pull requests on gitcode.com and github.com |
| [ssh-password-transfer](specialized/ssh-password-transfer/) | Copy files to/from remote servers over SSH with password auth |
| [xingyun-push](specialized/xingyun-push/) | Push/rebase/MR workflow for Xingyun (`coding<internal-domain>`) internal repos |
| [xingyun-reviewer](specialized/xingyun-reviewer/) | Monitor MR review comments, classify them, fix, self-test and reply |
| [opencode-skills-sync](specialized/opencode-skills-sync/) | Sync skills to this repo: YAML frontmatter validation + sanitization rules |
| [xllm-npu-deps-bundle](specialized/xllm-npu-deps-bundle/) | Build the unified xLLM NPU deps bundle (`xllm-deps-*.run`): compile the operator run packages and wheels declared in the bundled `npu_docker_depends.yaml`, assemble and verify the self-extracting bundle |
| [sync-after-squash-merge](specialized/sync-after-squash-merge/) | Re-sync a local branch after its MR was squash-merged into main (never pull/rebase/replay) |

## What is a "skill"?

A skill is a directory containing a `SKILL.md` file (plus optional scripts)
that teaches the agent how to handle a specific task. Skills are loaded
on-demand when the task matches the skill's trigger conditions — except the
meta-paradigms `user-communication` (governs all output) and `self-evolution`
(governs all skill authoring and maintenance).

```
skills/
  <category>/
    my-skill/
      SKILL.md          # frontmatter (name, description) + workflow instructions
      install.sh        # idempotent dependency installer (run on first use)
```

## Skill contract

Every skill directory must satisfy all of:

1. **Name matches the directory** — frontmatter `name` equals the directory
   basename, `[a-z0-9-]`, ≤64 chars; `description` ≤1024 chars, states when the
   skill triggers.
2. **Quoted YAML** — `description` is one double-quoted scalar. An unquoted
   value containing `: ` makes GitHub report
   `mapping values are not allowed here`.
3. **Dependency section** — a `## 依赖（首次使用自动安装）` block right after the
   title with a `| 依赖 | 检查 | 缺失时 |` table and a note to run
   `bash <skill-dir>/install.sh` on first use; the file `install.sh` must exist
   and be idempotent.
4. **Output paradigm block** — every skill except `user-communication` carries a
   `## 输出范式（所有技能统一）` block pointing back to
   `meta/user-communication`.

## Installation

Clone once, then **symlink** — every agent reads the same working copy, so a
`git pull` or a local edit takes effect everywhere on the next session:

```bash
git clone https://github.com/WiseEnjoy/oh-if-skills.git ~/git/oh-if-skills
REPO=~/git/oh-if-skills

# Codex / JoyCode and Claude Code: flat per-skill symlinks (skill name == link name)
for d in "$REPO"/{meta,common,specialized}/*; do
  ln -sfn "$d" ~/.codex/skills/$(basename "$d")
  ln -sfn "$d" ~/.claude/skills/$(basename "$d")
done

# OpenCode: category symlinks (it discovers nested dirs recursively)
for c in meta common specialized; do ln -sfn "$REPO/$c" ~/.config/opencode/skills/$c; done
```

Copying instead of symlinking also works, but then every update has to be
re-copied to each agent. Run each skill's `install.sh` once before first use —
it is idempotent and exits immediately when dependencies are already present.

## Writing your own skill

1. Create `skills/<category>/<name>/SKILL.md`
2. Add YAML frontmatter with `name` (== directory name) and a quoted
   `description` (determines when the skill activates — list trigger phrases)
3. Add the dependency section + `install.sh`
4. Add the output-paradigm block pointing to `meta/user-communication`
5. Write the workflow: what to do, in what order, with what checks
6. Include real failure cases and how to handle them (not just happy path)
7. Add self-test rules if the skill modifies code or pushes changes

## Contributing

PRs welcome. Each skill must:
- have a clear, specific trigger description
- include error handling, not just the happy path
- pass the YAML frontmatter validator (see
  [opencode-skills-sync](specialized/opencode-skills-sync/))
- not contain credentials, internal hostnames, IPs, or personal paths
  (sanitize before publishing — see the sanitization table in
  [opencode-skills-sync](specialized/opencode-skills-sync/))
- follow the skill contract above

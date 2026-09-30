# oh-if-skills

OpenCode / Claude Code agent skills collection — reusable workflows distilled
from real production experience.

## Skills

Two-level layout: `skills/<category>/<name>/SKILL.md`. OpenCode discovers
nested directories recursively, so copy the category folder too.

### common/ — shared disciplines (apply to every task)

| Name | Description |
| --- | --- |
| [user-communication](common/user-communication/) | **Meta-paradigm, not an optional skill**: every skill's outward output must satisfy it — chat replies, PR/MR bodies, review replies, error messages, summaries |
| [safe-ops-rules](common/safe-ops-rules/) | Safety checks before destructive operations (rm, kill, revert, re-run) |
| [long-running-commands](common/long-running-commands/) | Run long tasks (builds, tests, downloads) detached with `setsid`, without timeout kills |

### specialized/ — platform-specific workflows

| Name | Description |
| --- | --- |
| [gitcode-github-pr](specialized/gitcode-github-pr/) | Create, list, view and merge pull requests on gitcode.com and github.com |
| [ssh-password-transfer](specialized/ssh-password-transfer/) | Copy files to/from remote servers over SSH with password auth |
| [xingyun-push](specialized/xingyun-push/) | Push/rebase/MR workflow for Xingyun (`coding<internal-domain>`) internal repos |
| [xingyun-reviewer](specialized/xingyun-reviewer/) | Monitor MR review comments, classify them, fix, self-test and reply |
| [opencode-skills-sync](specialized/opencode-skills-sync/) | Sync skills to this repo: YAML frontmatter validation + sanitization rules |

## What is a "skill"?

A skill is a directory containing a `SKILL.md` file (plus optional scripts)
that teaches the agent how to handle a specific task. Skills are loaded
on-demand when the task matches the skill's trigger conditions — except the
meta-paradigm `user-communication`, which every skill's output must follow.

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
   `common/user-communication`.

## Installation

```bash
# clone and copy the categories (or single skills) you need
git clone https://github.com/WiseEnjoy/oh-if-skills.git
cp -r oh-if-skills/common oh-if-skills/specialized ~/.config/opencode/skills/
# or for project-specific skills:
cp -r oh-if-skills/common/<skill> <your-repo>/.claude/skills/
```

Run each skill's `install.sh` once before first use — it is idempotent and
exits immediately when dependencies are already present.

## Writing your own skill

1. Create `skills/<category>/<name>/SKILL.md`
2. Add YAML frontmatter with `name` (== directory name) and a quoted
   `description` (determines when the skill activates — list trigger phrases)
3. Add the dependency section + `install.sh`
4. Add the output-paradigm block pointing to `common/user-communication`
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

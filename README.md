# oh-if-skills

OpenCode / Claude Code agent skills collection — reusable workflows distilled
from real production experience.

## Skills

| Name | Description |
| --- | --- |
| [git-pr](git-pr/) | Create, list, view and merge pull requests on gitcode.com and github.com |
| [long-running-commands](long-running-commands/) | Run long tasks (builds, tests, downloads) without timeout kills |
| [safe-ops-rules](safe-ops-rules/ universal safety checks before destructive operations) | Safety checks before destructive operations (rm, kill, revert) |
| [scp-transfer](scp-transfer/) | Copy files to/from remote servers over SSH with password auth |
| [user-communication](user-communication/) | Universal output rules: clear, accurate, user-comprehensible language |
| [xingyun-push](xingyun-push/) | Push/PR workflow for JD Xingyun (coding.jd.com) internal repos |
| [xllm-pr-autofix](xllm-pr-autofix/) | Monitor PR review comments and auto-fix with self-tests |

## What is a "skill"?

A skill is a directory containing a `SKILL.md` file (plus optional scripts)
that teaches the agent how to handle a specific task. Skills are loaded
on-demand when the task matches the skill's trigger conditions.

```
skills/
  my-skill/
    SKILL.md          # frontmatter (name, description) + workflow instructions
    scripts/           # optional helper scripts
```

## Installation

```bash
# clone and copy the skills you need
git clone git@github.com:WiseEnjoy/oh-if-skills.git
cp -r oh-if-skills/<skill-name> ~/.config/opencode/skills/
# or for project-specific skills:
cp -r oh-if-skills/<skill-name> <your-repo>/.claude/skills/
```

## Writing your own skill

1. Create `skills/<name>/SKILL.md`
2. Add YAML frontmatter with `name` and `description` (description determines
   when the skill activates — be specific about trigger conditions)
3. Write the workflow: what to do, in what order, with what checks
4. Include real failure cases and how to handle them (not just happy path)
5. Add self-test rules if the skill modifies code or pushes changes

## Contributing

PRs welcome. Each skill must:
- have a clear, specific trigger description
- include error handling, not just the happy path
- not contain credentials, internal hostnames, or personal paths
- be self-contained (no dependencies on other skills unless explicitly stated)

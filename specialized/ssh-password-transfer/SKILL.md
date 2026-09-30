---
name: ssh-password-transfer
description: "用 SSH 用户名/密码把文件或目录拷贝到远程主机（或取回），处理内网主机（如 <internal-host>）只允许密码登录、且先报 publickey 会打断 SSH 流的坑。用户说 复制到 xxx / scp to host / 拷贝文件到远程 时使用。依赖 sshpass 与 rsync（缺失时 install.sh 自动安装，rsync 装不上退回 scp -O）。"
---

# ssh-password-transfer

## 依赖（首次使用自动安装）

| 依赖 | 检查 | 缺失时 |
| --- | --- | --- |
| `sshpass` | `command -v sshpass` | install.sh 自动安装 |
| `rsync` | `command -v rsync` | install.sh 自动安装；失败则退回 scp -O |
| `ssh` | `command -v ssh` | 环境预装，install.sh 自检 |

**首次使用**：加载本 skill 后、执行任何命令前，先跑一次
`bash <本skill目录>/install.sh`（幂等，依赖齐全立即退出 0）。
仍有缺失时脚本会逐项列出，按提示手动安装后再继续。
`<本skill目录>` = skill 工具输出里的 `Base directory for this skill`。


Copy files/directories to or from a remote Linux host using SSH password
authentication. Works for JD internal cluster hosts (e.g. `<internal-host>`) and
any host that only accepts password login.


## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `common/user-communication` skill 的 Principles 与 Banned patterns 自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## Required inputs

Collect from the user before running anything:

- `HOST` — hostname or IP (e.g. `<internal-host>`)
- `USER` — login username (e.g. `<your-username>` or `<your-username>`)
- `PASSWORD` — login password
- `SRC` — local source path (file or dir; use trailing `/` to copy dir *contents*)
- `DST` — remote destination dir (defaults to remote `$HOME` if not given)

If `DST` is omitted, first determine the remote home with:

```bash
sshpass -p "$PASSWORD" ssh $SSH_OPTS "$USER"@"$HOST" 'echo $HOME'
```

## Critical: force password auth

These hosts advertise `publickey` before `password` and break the SSH stream
("Bad packet length ... Connection corrupted" / "Received message too long")
when a public key is offered first. **Always** disable pubkey and force
password:

```bash
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no"
```

Verify connectivity and confirm the target dir exists before copying:

```bash
sshpass -p "$PASSWORD" ssh $SSH_OPTS "$USER"@"$HOST" 'pwd && ls -ld "'"$DST"'"'
```

## Copy commands

Prefer `rsync` (idempotent, resumable, shows progress). Use `--partial` for
large files so an interrupted transfer can be resumed.

```bash
RSSH="ssh $SSH_OPTS"
sshpass -p "$PASSWORD" rsync -avP --partial -e "$RSSH" "$SRC" "$USER"@"$HOST":"$DST"
```

Fallback when `rsync` is unavailable on either side (plain SCP protocol):

```bash
sshpass -p "$PASSWORD" scp -O $SSH_OPTS -r "$SRC" "$USER"@"$HOST":"$DST"
```

For single large files, `rsync --partial` + re-run resumes instead of
restarting from zero.

## Requirements & notes

- `sshpass` must be installed locally (`which sshpass`). If missing, install it
  or fall back to prompting for the password.
- The remote `$DST` directory must exist; `rsync`/`scp` will not create nested
  missing parents. Create it first if needed:
  `sshpass -p "$PASSWORD" ssh $SSH_OPTS "$USER"@"$HOST" 'mkdir -p "'"$DST"'"'`
- Never log the password into shell history beyond the command itself; avoid
  committing it to any file.
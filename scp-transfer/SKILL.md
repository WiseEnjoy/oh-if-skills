---
name: scp-transfer
description: Use when the user wants to copy files to/from a remote server over SSH with a username/password (e.g. "复制到 xxx", "scp to host", "拷贝文件到远程"). Handles the password-auth SSH quirk needed for JD internal hosts like <internal-host>.
---

# scp-transfer

Copy files/directories to or from a remote Linux host using SSH password
authentication. Works for JD internal cluster hosts (e.g. `<internal-host>`) and
any host that only accepts password login.

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
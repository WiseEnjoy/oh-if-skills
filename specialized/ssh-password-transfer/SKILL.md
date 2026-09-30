---
name: ssh-password-transfer
description: "用 SSH 用户名/密码把文件或目录拷贝到远程主机（或取回），处理内网主机（如 <internal-host>）只允许密码登录、且先报 publickey 会打断 SSH 流的坑。用户说 复制到 xxx / scp to host / 拷贝文件到远程 时使用。依赖 sshpass 与 rsync（缺失时 install.sh 自动安装，rsync 装不上退回 scp -O）。"
---

# ssh-password-transfer（用户名/密码 SSH 拷文件）

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

用 SSH 用户名/密码认证，把文件/目录拷到远程 Linux 主机，或从远程取回。
适用于内网集群主机（如 `<internal-host>`），以及任何只接受密码登录的主机。

## 输出范式（所有技能统一）

本 skill 产出的**一切对外内容**（对话回复、PR/MR 描述、评审回复、报错信息、结果汇总）
必须先按 `common/user-communication` skill 的原则与禁止写法自检后再发出：
用词准确无歧义、先上下文后结论、证据先行；不满足范式的输出不许发出。

## 必填输入

跑任何命令之前，先从用户那儿拿到：

- `HOST` — 主机名或 IP（如 `<internal-host>`）
- `USER` — 登录用户名（如 `<your-username>` 或 `<your-username>`）
- `PASSWORD` — 登录密码
- `SRC` — 本地源路径（文件或目录；目录后面加 `/` 表示拷目录*内容*）
- `DST` — 远程目标目录（不给则默认为远程 `$HOME`）

`DST` 没给时，先这样探出远程家目录：

```bash
sshpass -p "$PASSWORD" ssh $SSH_OPTS "$USER"@"$HOST" 'echo $HOME'
```

## 关键：强制密码认证

这些主机的认证协商里 `publickey` 排在 `password` 前面；一旦先递上公钥，
SSH 流就会被打断（`Bad packet length ... Connection corrupted` /
`Received message too long`）。**必须**禁用公钥、强制密码：

```bash
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no"
```

拷贝之前先验证连通性、确认目标目录存在：

```bash
sshpass -p "$PASSWORD" ssh $SSH_OPTS "$USER"@"$HOST" 'pwd && ls -ld "'"$DST"'"'
```

## 拷贝命令

优先用 `rsync`（幂等、可续传、有进度）。大文件加 `--partial`，
传输被打断后可以接着传。

```bash
RSSH="ssh $SSH_OPTS"
sshpass -p "$PASSWORD" rsync -avP --partial -e "$RSSH" "$SRC" "$USER"@"$HOST":"$DST"
```

任一侧没有 `rsync` 时退回纯 SCP 协议：

```bash
sshpass -p "$PASSWORD" scp -O $SSH_OPTS -r "$SRC" "$USER"@"$HOST":"$DST"
```

单个大文件用 `rsync --partial` + 重跑即可续传，不会从零开始。

## 要求与注意

- 本地必须装好 `sshpass`（`which sshpass`）。没有就装，或者退回手动输密码。
- 远程 `$DST` 目录必须存在；`rsync`/`scp` 不会补建缺失的多级父目录。
  需要的话先建：
  `sshpass -p "$PASSWORD" ssh $SSH_OPTS "$USER"@"$HOST" 'mkdir -p "'"$DST"'"'`
- 密码不要写进 shell 历史（命令本身就是上限），更不要提交到任何文件里。

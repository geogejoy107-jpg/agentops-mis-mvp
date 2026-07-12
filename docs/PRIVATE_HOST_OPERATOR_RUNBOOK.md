# AgentOps MIS 私有 Host 与远程操控台运行手册

状态：目标运行手册，命令是否可用以当前实现验收为准
适用范围：一台受信任电脑运行 AgentOps MIS 与 AI Runtime，另一台电脑仅通过 Tailscale 和浏览器操控

## 1. 使用边界

本模式把两台电脑分成两种角色：

- **Host 主机**：保存 SQLite 权威账本、知识库、项目文件和批准后的产物，并运行 AgentOps MIS、Hermes、OpenClaw 与 Worker。
- **Console 操控端**：只打开受认证的浏览器工作台，用于创建任务、监督运行、审批、评估、记忆审核、审计查看和批准产物下载。

操控端不需要 Git、Python、Node、仓库副本、Hermes 或 OpenClaw。模型密钥、Agent 凭据、数据库、知识库原文、raw prompt/response 和运行日志不应传到操控端，也不得进入 Git 仓库。

本版本只规划 **Tailscale Serve 私网预览**：Host 应继续监听 loopback，由 Tailscale 提供设备私网和 HTTPS 入口。不得自动执行 Tailscale 配置，不得自动开放路由器端口，不得绑定公网，也不得把该模式宣传为公开 SaaS。

> 下文 `agentops host ...` 是产品目标命令。只有对应实现、smoke、第二电脑验收和 Release 证据通过后，才可视为已发布能力。若当前安装返回 unknown command，应回到仓库当前验收文档，不要用手工公网暴露绕过缺失功能。

## 2. 上线前检查

Host 主机应满足：

- 使用受支持的 AgentOps MIS 版本化安装资产或明确标注的开发预览；
- Tailscale 已由用户手动安装并登录到受信任的 tailnet；
- 本地磁盘有足够空间保存账本、知识索引和批准产物；
- Hermes/OpenClaw 如需真实运行，已由主机管理员单独安装并通过本地健康检查；
- 没有把 token、`.env`、SQLite DB、raw prompt/response、私聊或完整 transcript 放进仓库；
- 确认本轮不会自动安装或启用 Hermes/OpenClaw，Runtime 自动安装留待后续版本。

Console 电脑只需要：

- Tailscale 客户端，并加入与 Host 相同的受信任 tailnet；
- 现代浏览器；
- Host 管理员提供的 HTTPS Console URL 和一次性设置/邀请信息。

## 3. 安装版本化 Host 预览

下一修正版候选：

```text
v1.6.0-private-host-preview.4
https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.4
```

下载前确认该 Release 已实际发布，并同时下载 `.zip` 或 `.tar.gz` 与
`.sha256.json`。发布附件中的 checksum manifest 是当前候选的权威校验
来源；本运行手册不把 archive checksum 写回同一 archive，避免自引用。

preview.2 已发布但随后被真实 Runtime dogfood 替代：安装版 Worker 能
claim 任务，但 Agent Plan 在 `run_start` 前发现 archive 缺少
`PROJECT_SPEC.md`、`AGENT_WORKFLOW.md`、`BASE_INDEX.md` 与
`docs/AGENT_WORK_METHOD_BLOCK.md`，因此按设计 fail closed，未调用模型。
preview.4 在 preview.3 的 Agent Plan 与真实 Runtime 闭环基础上，增加
异步断线后完成、幂等提交、SQLite CAS 启动租约和 workspace 隔离验收。
它仍是预览版本；物理第二设备和另一台 Mac 验收通过前不得称为正式 RC。

已发布但被替代的预览版本：

```text
v1.6.0-private-host-preview.1
https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.1
```

该版本发布了以下三个资产：

```text
agentops-mis-private-host-1.6.0-private-host-preview.1.zip
agentops-mis-private-host-1.6.0-private-host-preview.1.tar.gz
agentops-mis-private-host-1.6.0-private-host-preview.1.sha256.json
```

preview.1 发布页记录的历史 SHA-256：

```text
zip      624e4ec9cb954bcf208ebf5840d535b07142a1557ba61be649de25f22e97b43f
tar.gz   e68bfae7e29a4f7356db4b162a965d29579ccaf2c9fc2a5ba3584c7440966e0a
manifest a7889a858801b4ef0fc4579d0f9e796b4b597395536417c2a9ac32497cd344ad
```

Release 下载验证发现 preview.1 的安装 shim 在源码 checkout 或继承的
`PYTHONPATH` 环境中可能被源码遮蔽，导致 packaged version provenance
读错；该 Release 已标记 **Superseded preview**。不要再把它作为当前安装
候选。修正版 preview.2 必须在 exact-head CI、资产 checksum、GitHub 下载
和干净安装复验完成后，才会在这里列为当前候选。即使 preview.2 通过，
在第二设备验收完成前也不能称为正式 RC。

从 GitHub Private Host prerelease 下载同一版本的三个文件：

```text
agentops-mis-private-host-<version>.tar.gz 或 .zip
agentops-mis-private-host-<version>.sha256.json
```

先在下载目录独立计算 archive 的 SHA-256，并与 JSON 中对应文件名的
值逐字比较。校验不一致时不得解压或执行安装器。以 macOS 自带命令为
例：

```bash
shasum -a 256 agentops-mis-private-host-<version>.tar.gz
python3 -m json.tool agentops-mis-private-host-<version>.sha256.json
```

校验通过后解压并在 bundle 根目录执行：

```bash
tar -xzf agentops-mis-private-host-<version>.tar.gz
cd agentops-mis-private-host-<version>
sh install.sh
export PATH="$HOME/.local/bin:$PATH"
agentops host version
```

该 unsigned developer preview 需要主机已有 Python 3.10+；安装过程不联网，
不安装 Node、Git、Hermes、OpenClaw 或 Tailscale。安装器会再次按
`manifest.json` 校验每个文件，拒绝篡改、遗漏、未声明文件和路径穿越。
默认程序位于 `~/.local/share/agentops-mis`，数据位于
`~/.agentops/host`。操控端电脑不执行本节，它仍然只需要 Tailscale 和
浏览器。

## 4. 目标初始化流程

### 4.1 初始化 Host

```bash
agentops host init
```

目标行为：

- 在仓库外创建权限受限的运行目录；
- 检查生产 UI、Python 服务、SQLite、知识索引和端口条件；
- 初始化本地 Host 配置和 Owner bootstrap 流程；
- 默认保持 loopback，不启动 Tailscale Serve；
- loopback HTTP Session 使用 `HttpOnly`、`SameSite=Strict` Cookie，但不错误添加仅限 HTTPS 的 `Secure` 属性；
- 不安装、不启动 Hermes/OpenClaw，不读取现有 Runtime 密钥；
- 不把 setup code、Session、DB 或运行日志写入仓库。

初始化后先运行：

```bash
agentops host doctor
agentops host status
```

任一关键检查失败时，应先按 `doctor` 的本地修复建议处理，不要改成 `0.0.0.0` 或开放公网端口作为替代方案。

### 4.2 启动 Host

```bash
agentops host start
```

目标行为：

- 启动同源生产 UI、MIS API、SQLite 账本和知识索引；
- 不依赖运行时 Vite 开发服务器；
- 默认只监听 loopback；
- 打印本机 Console URL，但不在 URL 中携带任何凭据；
- Hermes/OpenClaw 未就绪时显示 `unavailable`，而不是伪装为真实运行成功；
- 真实 Agent 任务仍需明确启用并确认。

启动后检查：

```bash
agentops host status
agentops host doctor
agentops host console-url
```

预期至少能区分：Host 进程、生产 UI、API、账本、知识索引、Worker 和 Runtime adapter 的 `ready`、`degraded` 或 `unavailable` 状态。

### 4.3 查看日志

```bash
agentops host logs
```

日志输出必须经过脱敏。不得显示 setup code、密码、Session、CSRF、Agent token、模型密钥、完整 prompt/response 或任意数据库内容。需要持续观察时，以实现支持的参数为准，不要假定 `--follow` 已发布。

## 5. Tailscale Serve 预览

先只生成并审查预览：

```bash
agentops host tailscale-preview --https-port 8443
```

目标输出应包含：

- 检测到的 Tailscale 状态；
- 拟使用的本地 loopback 上游；
- 拟生成的 tailnet HTTPS Console URL；
- 用户需要手动执行的 Tailscale Serve 命令；
- 当前未执行任何网络变更的明确提示；
- 停止和撤销 Serve 的对应命令。

`tailscale-preview` 只能做只读检查和命令预览，不得：

- 自动运行 `tailscale serve`；
- 自动修改 ACL、DNS、路由器或防火墙；
- 自动启用 Funnel；
- 暴露公网；
- 把 token、setup code 或 Session 放进 URL、终端历史或日志。

macOS 上，CLI 会先查找 `PATH`，随后自动识别 `/Applications/Tailscale.app/Contents/MacOS/Tailscale`。特殊安装位置可以通过 `AGENTOPS_TAILSCALE_BIN` 显式指定；该变量只应指向可执行文件路径，不应包含认证信息。

管理员审查预览后，显式确认应用：

```bash
agentops host tailscale-apply --https-port 8443 --confirm
agentops host restart
```

命令调用当前 Tailscale CLI 的 `serve --https=<port> --bg`，只代理 Host loopback 地址，随后把
tailnet HTTPS Origin 写入私有 Host 配置并启用 `Secure` Session Cookie。没有 `--confirm` 时必须保持零副作用；
该路径不得调用 `tailscale funnel`。如果 `443` 已被 OpenClaw 或其他本地服务使用，优先选择独立端口（例如 `8443`），不得默认替换现有 Serve 入口。

启用后重新检查：

```bash
agentops host status
agentops host doctor
agentops host console-url
```

`console-url` 应只输出不含凭据的 HTTPS 地址。另一台电脑加入同一 tailnet 后，在浏览器中打开该地址，完成 Owner 初始化或登录。未认证用户不得读取 workspace 数据。

## 6. 另一台电脑的操作流程

正式逐项协议与 bounded evidence 字段见
`docs/PRIVATE_HOST_SECOND_DEVICE_ACCEPTANCE.md`。浏览器生成的 device
checklist 只用于现场操作提醒，必须标记 `non_authoritative:true`；最终验收
回执必须由 Host 根据权威账本生成并计算 payload hash。

1. 手动安装并登录 Tailscale，确认与 Host 位于同一受信任 tailnet。
2. 在浏览器打开 `agentops host console-url` 给出的 HTTPS 地址。
3. 使用一次性设置/邀请流程建立人类账号，不使用 Agent Gateway 机器 token 登录浏览器。
4. 查看 Host、账本、知识索引、Worker 和 Runtime readiness。
5. 创建一条低风险任务并派发给可用团队。
6. 观察任务被 claim、Run 启动、Runtime Event、Evaluation、Artifact 和 Audit 写回。
7. 如出现 prepared action，在审批中心由有权限的人批准或拒绝。
8. 只下载明确批准的 ID 化产物；浏览器不得获得 Host 的任意文件路径。
9. 关闭或断开浏览器后，Host Worker 应继续运行；重新连接只恢复观察，不应重启任务。

真实 Hermes/OpenClaw 验收必须使用新鲜任务和明确确认。Mock 仅用于离线/CI 回退，并应在界面和录屏中标记为 Mock。

仓库或开发预览内置的真实验收客户端可以通过人类 Session 派发同一条客户闭环，而不是绕过 Private Host 认证。临时密码和一次性 setup code 只能放在当前 shell 的 `AGENTOPS_ACCEPTANCE_PASSWORD`、`AGENTOPS_OWNER_SETUP_CODE` 环境变量中，然后使用 `customer_worker_real_runtime_acceptance.py --human-auth --confirm-live`；不得把值写进命令行参数、文档、日志或 Git。

## 7. 日常生命周期

```bash
agentops host status
agentops host doctor
agentops host logs
agentops host restart
agentops host stop
agentops host backup
agentops host backup-verify
```

- `status`：查看受管进程、版本、端口和组件状态，不输出 workspace 私密数据。
- `doctor`：做只读诊断，并给出可操作修复建议；不得静默修改网络或 Runtime。
- `logs`：查看脱敏后的 Host 日志。
- `restart`：只重启该 Host 拥有的进程，保留账本和知识状态。
- `stop`：停止 Host 服务和受管 Worker，不删除 DB、知识库、配置或备份。
- `backup`：通过 SQLite 在线备份 API 创建带 SHA-256 manifest 的本地账本备份；Host 可以继续运行。
- `backup-verify`：只读校验最新或指定备份的 SHA-256 与 SQLite integrity，不打印账本行。

命令的精确参数、服务管理方式和退出码均以当前实现验收为准。发布前必须证明重启不丢状态、停止不误杀其他进程。

### 7.1 备份与恢复

创建并校验备份：

```bash
agentops host backup
agentops host backup-verify
```

默认备份目录为 `~/.agentops/host/backups`，目录权限为 `0700`，SQLite 备份和 manifest 权限为 `0600`。备份包含完整权威 SQLite 账本，包括 hash-only Session/Token 状态，因此仍须作为敏感文件保护；它不复制 `secrets.json`、Host 日志、PID、原始 Runtime 密钥或 raw prompt/response。

恢复前必须停止 Host，并先校验选定备份：

```bash
agentops host stop
agentops host backup-verify --backup /path/to/agentops-mis-YYYYMMDDTHHMMSSZ.sqlite
agentops host restore \
  --backup /path/to/agentops-mis-YYYYMMDDTHHMMSSZ.sqlite \
  --confirm-restore
agentops host start
```

没有 `--confirm-restore` 时恢复保持 dry-run；Host 进程仍运行时恢复会失败关闭。缺少 manifest、文件 hash/size/schema 不匹配、SQLite integrity 或 foreign-key 检查失败时也会拒绝恢复。覆盖现有账本前会创建并验证同目录的 `.pre-restore-<timestamp>` SQLite 安全快照，随后通过同目录临时文件原子替换。

恢复不会替换当前 Host 的独立密钥文件。为避免旧备份复活已经撤销的访问权限，恢复后的 `human_sessions`、`agent_gateway_sessions` 和长期 `agent_gateway_tokens` 会默认统一撤销；Owner 需要重新登录，Agent 需要重新 enrollment。

这一版只证明 SQLite 权威账本的产品命令闭环。Host 外部项目目录或未来可变 Markdown 知识源仍需要单独的目录级备份策略，不能把本命令宣传成整机灾备。

### 7.2 版本升级与二进制回滚

先停止 Host 并检查当前版本：

```bash
agentops host stop
agentops host version
agentops host update --check
```

`update --check` 是离线只读检查，不会访问 GitHub 或自动下载。管理员下载并校验更高版本的 bundle 后，运行该 bundle 自带的 `install.sh`。安装器在 Host PID 存活时拒绝升级；如已有账本，会先用旧版本工具创建并校验 pre-update 备份，失败则拒绝升级。随后将新版本写入临时目录，原子切换 `current`，并保留 `previous` 指针；`~/.agentops/host` 数据目录不随程序版本移动。

如新版本启动验收失败，保持 Host 停止并执行：

```bash
agentops host rollback
agentops host rollback --confirm-rollback
agentops host start
```

第一条只显示 dry-run。确认回滚前，CLI 会先创建并校验当前 SQLite 账本备份，再原子交换 `current`/`previous` 二进制指针。当前版本尚无自动 schema downgrade；如果未来版本引入不向后兼容的数据库迁移，必须在 Release 级迁移策略中增加对应 downgrade 或数据恢复步骤，不能只靠切换二进制。

## 8. 录屏建议

建议录制 4 至 6 分钟的连续闭环，而不是逐页浏览 Dashboard：

1. **Host 终端**：展示 `agentops host status`、`doctor` 和 `console-url`；遮挡用户名、设备名及任何敏感信息。
2. **网络边界**：展示 `agentops host tailscale-preview` 明确写着 preview/no changes，并说明没有公网暴露。
3. **第二电脑登录**：只展示 Tailscale 已连接和浏览器登录页，强调该电脑没有项目依赖或 Agent Runtime。
4. **远程派发**：创建一条具体客户任务，选择 Host 上已就绪的 Hermes 或 OpenClaw，并进行显式确认。
5. **断线证明**：关闭第二电脑页面片刻，在 Host 或重新连接后的 Worker 页面展示任务仍在运行。
6. **证据闭环**：展示最新任务的 Run、Runtime Events、Tool Calls、Evaluation、Artifact、Approval 和 Audit；不要展示 raw prompt/response。
7. **知识边界**：展示有界检索引用或已批准记忆，说明完整知识库仍留在 Host。
8. **收尾撤销**：展示退出登录、停止 Host 和撤销 Tailscale Serve 的步骤。

最有说服力的三张截图：

- Host 状态页或终端：生产 Host、账本、知识索引与 Hermes/OpenClaw readiness 同时可见；
- 第二电脑浏览器：远程任务与 Worker 状态同屏，地址栏是 tailnet HTTPS 地址且不含 token；
- 新鲜 Run 详情：任务、事件、评估、批准产物和审计链路同屏。

录制前关闭系统通知，使用 16:9 画面，并检查画面中没有 `.env`、token、DB 路径、private message、完整 transcript、raw prompt/response 或未经批准的产物。

## 9. 故障排查

### Host 命令不存在

说明当前安装尚未包含该产品切片。检查版本和当前 Release 验收记录。不要把 `run_local_stack.py` 或 Vite 开发服务器直接暴露给第二电脑来模拟 Host 产品。

### Host 启动失败

依次运行：

```bash
agentops host status
agentops host doctor
agentops host logs
```

检查端口占用、生产 UI 资产、运行目录权限、磁盘空间和数据库可写性。不要删除现有 DB 作为第一修复手段。

### 第二电脑无法打开 Console

- 确认两台电脑位于同一 tailnet；
- 确认 Host 本地服务仍为 loopback ready；
- 重新运行 `tailscale-preview`，比较当前 Serve 状态与预期；
- 确认使用 `console-url` 的 HTTPS 地址，而非 Host 的 `127.0.0.1`；
- 检查 Tailscale ACL/DNS，不要改用公网端口转发。

### 页面能打开但无法登录或写入

- 检查人类 Session 是否过期或被撤销；
- 检查账号角色是否允许派发、审批或管理；
- 检查 Host 时间是否准确；
- 通过 `doctor` 检查 allowed origin、Secure Cookie 和 CSRF 状态；
- 不要把 Agent Gateway token 粘贴到浏览器作为替代凭据。

### Agent 显示 unavailable

这表示 Host 上对应 Runtime 未安装、未启动或健康检查失败。浏览器操控端无需安装 Runtime。由 Host 管理员在本机修复 Hermes/OpenClaw，并再次运行 `doctor`。第一阶段不提供 Runtime 自动安装。

### 浏览器断开后任务停止

这是验收失败，而不是正常行为。检查 Worker 是否由 Host 生命周期管理、是否错误绑定到浏览器请求，以及重连后是否能查询同一 task/run。保留脱敏日志和 ID 供排查，不保存 raw prompt/response。

## 10. 停止、退出与撤销

先让远程操作者退出登录，再在 Host 执行：

```bash
agentops host stop
agentops host status
```

然后显式撤销 Tailscale Serve 并重启 Host：

```bash
agentops host tailscale-revoke --confirm
agentops host restart
```

撤销内部使用与 apply 相同端口的 `tailscale serve --https=<port> off`，只移除 MIS 入口和对应私网 HTTPS trusted Origin，不清空其他 Serve 服务。确认：

- `console-url` 不再可从另一台电脑访问；
- Host 受管进程已停止；
- 未删除 SQLite、知识库、项目文件或备份；
- 没有 token、DB、日志、缓存或生成产物进入 Git 状态。

如需撤销浏览器访问，应从 Host 撤销对应人类 Session/设备授权；精确命令和 UI 以实现验收为准。删除 Tailscale 设备、修改 tailnet ACL 或清理 Host 数据属于独立高影响操作，不应由 `host stop` 自动执行。

## 11. 发布验收口径

只有以下证据同时存在，才能把本手册描述为正式可用流程：

- 版本化 Host 安装资产及 SHA-256；
- `init/start/status/doctor/logs/stop/restart/console-url/tailscale-preview` 的命令 smoke；
- 生产 UI 同源服务，不依赖运行时 Node/Vite；
- 第二电脑仅凭 Tailscale 和浏览器完成认证与客户任务闭环；
- 未认证读取、错误角色、CSRF、错误 Origin 和撤销 Session 均 fail closed；
- Console 断线不影响 Host Worker，Host 重启不丢账本和知识状态；
- 新鲜、显式确认的 Hermes/OpenClaw 运行证据；
- 停止和撤销 Tailscale Serve 验收；
- exact-head CI、secret scan、干净安装、备份恢复和 Release provenance 通过。

在上述验收完成前，本文件是产品操作契约和录屏准备依据，不是“功能已经全部发布”的声明。

# 项目规则

SL-crawler / InfoScraper —— 主程序 `main.py`，Windows 桌面采集工具，用 PyInstaller 打包、Inno Setup 制作安装包。

## 常用命令

```bash
pip install -r requirements.txt          # 安装依赖
python -m pytest -q                      # 跑全部测试（当前基线 142 passed）
python main.py                           # 本地启动 GUI
```

改动代码后必须跑 `pytest`，基线为 **142 passed**。测试失败时不要提交。

## 版本号

版本号存在于两个位置，**必须保持一致**：

- `version.py` 中的 `__version__`
- `installer/setup.iss` 中的 `#define MyAppVersion`

发布时 `release.yml` 会按 tag 自动改写这两处并在发布成功后提交回 `main`（提交信息**不带** `[skip ci]`，因为若 tag 指向含 `[skip ci]` 的提交，GitHub 会跳过该 tag 触发的发布工作流）。
因此**不要手工改版本号**，只要打对 tag 即可。

改写脚本必须保留 `-NoNewline` 并显式补 CRLF，两个文件都以 CRLF 结尾；否则同版本重写也会产生假差异，导致每次发布多出一个空提交。

## 发布流程

1. 确认 `main` 分支 CI 全绿
2. 打 annotated tag 并推送：
   ```bash
   git tag -a v4.x.y -m "v4.x.y"
   git push origin v4.x.y
   ```
3. `release.yml` 自动完成：构建 exe → 生成 zip → Inno Setup 编译安装包 → 生成 SHA256SUMS → 发布 Release → 回写版本号
4. 验证产物：4 个 asset 应齐全（`InfoScraper.exe`、`InfoScraper-Setup.zip`、`InfoScraper-Setup.exe`、`SHA256SUMS.txt`）

**不要手工提交 `dist/`、`setup_output/` 等构建产物**，它们已在 `.gitignore` 中，产物只通过 Release 分发。

## CI 运行器

| 工作流 | 运行器 | 说明 |
|---|---|---|
| `ci.yml` test | `ubuntu-24.04` + `ubuntu-26.04` | 双版本矩阵，覆盖 26.04 迁移窗口 |
| `ci.yml` build-windows | `windows-2022` + `windows-2025` | 验证 PyInstaller 与 exe 启动 |
| `release.yml` | `windows-2022` | 固定版本，保证与测试环境同为 VS2022 工具链 |

**不要使用 `ubuntu-latest` / `windows-latest`**：这两个浮动标签会随 GitHub 的镜像迁移静默切换底层工具链。`windows-latest` 与 `windows-2025` 目前均指向 `windows-2025-vs2026`，只有 `windows-2022` 仍保证 VS2022。

所有 Actions 需使用 Node 24 版本：`checkout@v7`、`setup-python@v7`、`upload-artifact@v7`、`softprops/action-gh-release@v3`。Node 20 已于 2026-09-23 停止支持。

## 依赖的 Action 与 runner 版本

升级前先确认 `action.yml` 中的 `using: node24`，再改版本号：

```bash
gh api repos/actions/checkout/releases/latest --jq '.tag_name'
```

## 网络

本机到 `github.com` 的 443 端口不稳定，DNS 解析出的 IP 有时不可达。已配置：

- git 全局代理：`http://127.0.0.1:7897`（写入 `~/.gitconfig` 的 `http.proxy` / `https.proxy`）
- 用户级环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`（供 `gh` 等工具使用）

代理依赖 Clash Verge 运行（端口 7897）。若 Clash 未启动，git 会报 `Failed to connect to 127.0.0.1 port 7897`。
临时绕过代理：

```bash
git -c http.proxy= -c https.proxy= push origin main
```

`gh` CLI 读取环境变量而非 git 配置，与 git 是两条独立链路。

## 仓库约定

- 提交信息使用中文，遵循 `type: 描述` 格式（`ci:` / `chore:` / `fix:` / `feat:`）
- 不要在代码中添加注释，除非有必要解释非显而易见的逻辑
- 远程仓库：`https://github.com/tomjoy248-crypto/InfoScraper.git`
- 文档中的下载链接统一使用 `releases/latest` 形式，不写具体版本号，避免发版后失效

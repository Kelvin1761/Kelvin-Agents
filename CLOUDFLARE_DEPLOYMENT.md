# Cloudflare Deployment Setup

呢份文件只講目前 repo 已支援嘅 Cloudflare deployment setup，同埋另一部機 clone repo 之後要點樣安全配置。

## Current Status

目前 HKJC / AU analysis snapshot deploy 係 **支援** 嘅。

現行 deploy path：

- repo root wrapper: `./deploy.sh`
- actual script: `Horse_Racing_Dashboard/deploy.sh`
- Cloudflare Pages project default: `wongchoi-dashboard`

目前唔需要 Worker name。
目前用緊嘅係 **Cloudflare Pages project**。

## What Is Already In The Repo

- [deploy.sh](deploy.sh)
- [Horse_Racing_Dashboard/deploy.sh](Horse_Racing_Dashboard/deploy.sh)
- [Horse_Racing_Dashboard/wrangler.toml](Horse_Racing_Dashboard/wrangler.toml)
- AU / HKJC post-success hook:
  `.agents/skills/shared_racing/post_success_hooks/scripts/cloudflare_deploy_hook.py`

目前 orchestrator 成功完成後會 best-effort 自動嘗試 deploy，除非你：

- 加 `--skip-cloudflare-deploy`
- 或設 `WC_DISABLE_POST_SUCCESS_DEPLOY=1`

## What Another Computer Needs

### 1. Node.js / npx

deploy script 會用：

```bash
npx wrangler pages deploy ...
```

所以另一部機至少要有：

- `Node.js`
- `npx`
- macOS / Linux：直接跑 `./deploy.sh`
- Windows：建議用 `Git Bash`、`WSL`，或者明確跑 `bash deploy.sh`

### 2. Cloudflare authentication

你有兩種方式：

#### Option A: Wrangler login

```bash
npx wrangler login
```

適合本機手動 deploy。

#### Option B: Environment variables

適合另一部機、CI、或唔想用互動 login。

至少準備：

```bash
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
```

Windows PowerShell：

```powershell
$env:CLOUDFLARE_API_TOKEN="..."
$env:CLOUDFLARE_ACCOUNT_ID="..."
```

## Required Cloudflare Values

### Required

- `CLOUDFLARE_API_TOKEN`
  用嚟授權 `wrangler pages deploy`
- `CLOUDFLARE_ACCOUNT_ID`
  建議明確設置，尤其係另一部機或 token auth

### Repo-level setting already known

- Pages project name default:
  `wongchoi-dashboard`

如需改 project name，可設：

```bash
export WC_CLOUDFLARE_PAGES_PROJECT="your-pages-project"
```

Windows PowerShell：

```powershell
$env:WC_CLOUDFLARE_PAGES_PROJECT="your-pages-project"
```

### KV namespace

`wrangler.toml` 目前已綁定：

- `WC_STATE`

佢引用嘅 namespace id 已經寫喺 repo config，但呢個 **唔係 secret**。
真正 secret 仍然係 token，**唔可以 commit 入 GitHub**。

## How To Deploy Manually

### Build only

```bash
./deploy.sh --build-only
```

Windows 如使用 Git Bash / WSL：

```bash
bash deploy.sh --build-only
```

### Deploy

```bash
./deploy.sh
```

Windows 如使用 Git Bash / WSL：

```bash
bash deploy.sh
```

### Keep the generated dist folder

```bash
./deploy.sh --keep-dist
```

可同樣寫成：

```bash
bash deploy.sh --keep-dist
```

## How The Auto-Deploy Hook Works

以下主流程成功完成後，會自動 best-effort call `deploy.sh`：

- `HKJC Wong Choi`
- `AU Wong Choi`

如果 wrangler / auth / Node 環境未就緒：

- analysis 本身唔會因此 fail
- deploy 只會打印 warning

## Recommended Setup For Another Computer

clone repo 後：

1. 完成 [SETUP.md](SETUP.md)
2. 安裝 Node.js
3. Windows 用戶先確認可以用 `Git Bash` / `WSL` 跑 Bash script
4. 選擇 `wrangler login` 或 env-var auth
5. 設 `WC_CLOUDFLARE_PAGES_PROJECT`，如果唔係用預設 project
6. 跑：

```bash
./deploy.sh --build-only
./deploy.sh
```

## Security Rules

絕對唔好 commit：

- `CLOUDFLARE_API_TOKEN`
- `.env`
- shell history
- 本機 auth cache
- 任何 account-specific private config

Cloudflare credentials 應只以：

- shell env vars
- CI secret store
- Wrangler local login session

存在。

## What Is Still Missing Or Assumed

目前 repo 已支援 deploy，但以下資料唔會自動幫你創建：

- Cloudflare account access
- API token
- target Pages project ownership / permissions

即係話：

- **deploy flow 係支援**
- **credentials provisioning 仍然要人手做**

呢個係目前最乾淨、最安全嘅做法。

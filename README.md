# stockanalysis

可复用的 **A 股盘面定量复盘 + 定时邮件** 工具包。  
适合 fork 后自己配置邮箱；**不包含**任何人的私有分析报告或 API 密钥。

## 仓库里有什么

| 路径 | 说明 |
|---|---|
| `scripts/fetch_market_data.py` | 东方财富公开接口拉涨跌停等 |
| `scripts/generate_daily_quant_review.py` | 生成定量复盘 Markdown（无 LLM） |
| `scripts/send_report_email.py` | SMTP 发邮 |
| `scripts/run_daily_email.sh` | 本地一键：拉数 → 出稿 → 发邮 |
| `.github/workflows/daily-market-email.yml` | 工作日定时（默认北京 20:30） |
| `knowledge/` | 短线执行心法等**方法论**（可选读） |

个人复盘 md/pdf、个股报告、DCF 输入、`.env` 等默认在 `.gitignore`，只留在你本机。

## 快速开始

```bash
git clone https://github.com/Jhonwivk/stockanalysis.git
cd stockanalysis
cp .env.example .env
# 编辑 .env：SMTP_* 与 EMAIL_TO
chmod +x scripts/*.sh
./scripts/run_daily_email.sh          # 默认今天（上海时区）
./scripts/run_daily_email.sh 20260715 # 指定交易日
```

### 163 / QQ / Gmail

在邮箱设置中开启 SMTP，使用**授权码**填入 `SMTP_PASS`，不要用登录密码。

| 服务 | SMTP_HOST | PORT |
|---|---|---|
| 163 | `smtp.163.com` | 465 |
| QQ | `smtp.qq.com` | 465 |
| Gmail | `smtp.gmail.com` | 465 |

### GitHub Actions

1. Fork / push 本仓库  
2. Settings → Secrets and variables → Actions，添加：

`SMTP_HOST` · `SMTP_PORT` · `SMTP_USER` · `SMTP_PASS` · `EMAIL_TO` · `EMAIL_FROM` · `SMTP_SSL`（可选 `EMAIL_FROM_NAME`）

3. 修改定时：编辑 `.github/workflows/daily-market-email.yml` 里的 `cron`（UTC）

Secrets **只存在于你的仓库设置里**，不会写进代码。

## 安全约定

- **禁止**把 `.env`、授权码、Token、私人研报提交进 git  
- 自动邮件发送的是**定量公开行情摘要**，不是带私有 API 的内容  
- 正式 Agent 叙事复盘请在本机生成；需要的话可本地附带到邮件（见 `run_daily_email.sh`），但不要 push 报告文件

## 说明与免责

定量稿主线标签为脚本粗判；近窗样本若用于自测，目的是**验证逻辑**，不是永久军规。  
所有输出仅供研究，不构成投资建议。

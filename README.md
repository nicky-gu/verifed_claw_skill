# Verified Claw Skills - AI Agent Skill Security Audit

🛡️ 对 [Skillhub](https://clawhub.com) 公开仓库中所有 AI Agent 技能进行安全审计，基于 [skill-vetter](https://clawhub.com/openclaw-skill-vetter) 协议。

## 审计范围

- **Skillhub 公开仓库**: 15,269 个技能
- **审计协议**: skill-vetter (Source Check → Code Review → Permission Scope → Risk Classification)
- **RED FLAGS 检测**: 反弹 shell、凭据窃取、数据外传、混淆代码、sudo 权限、系统文件修改等

## 风险等级

| 等级 | 说明 |
|------|------|
| ⛔ EXTREME | 发现恶意模式，建议禁止安装 |
| 🔴 HIGH | 连接未知服务器、需 sudo、读取环境变量，需安全审批 |
| 🟡 MEDIUM | 注册系统服务、安装外部包，需谨慎 |
| 🟢 LOW | 未发现明显风险，可安全安装 |

## 链接

- 📊 [完整审计报告（可搜索/筛选）](index.html)

## 更新日志

- 2026-04-10: 初始审计，覆盖 15,269 个技能

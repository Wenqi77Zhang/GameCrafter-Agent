# GameCrafter

> 将可追溯的游戏资料，变成可审核、可拍摄的海外短视频营销方案。

GameCrafter 是面向游戏开发者和营销人员的个人开源 AI 应用。默认简体中文界面，
支持切换英文；首个验证场景为《异环》（NTE）面向英语地区的 TikTok 营销。

项目当前处于 **M19 真实创作链路质量验证阶段**，不是已完成商业验证的成熟 SaaS。
部署工作暂缓。代码检查、真实模型输出质量、真实用户验收和线上运行是四个独立状态；
具体结果见 [本轮实现与验收记录](docs/product/real-creative-workflow.md)。

当前已确认的质量缺口：本地模型仍会漏报和误报。最新 **14 例 × 2 轮，20/28 次符合预期**；
16 次负例判断中漏报 6 次，12 次正例判断中误报 2 次。这是开发回归集，不是总体准确率。
接口成功、规则满分或模型初审通过都不代表文案已合格；不应无人值守交付或照搬模型修改意见。

## 用户最终得到什么

1. **可追溯知识**：官方网页或明确导入的本地资料 → 精确引文 → 候选事实 → 审核后的知识版本。
2. **可读营销建议**：一个具体方向、话题、理由、英语开场 A/B、拍摄步骤、风险和验证计划。
3. **可编辑的英语分镜稿**：逐镜口播、字幕、画面要求、时间段和事实引用。
4. **可检查的交付**：独立模型评审、规则检查、真实版本修订与差异、人工终审、Markdown/JSON 导出。

生成的是**营销方案和脚本**，不是成片。不会自动发布 TikTok，不保证播放量或转化率；
官网公开资料也不等同于厂商内部 GDD。

## 当前能力和诚实边界

| 模块 | 实际实现 | 不能据此宣称 |
|---|---|---|
| 来源与知识 | NTE 白名单网页采集、局部浏览器回退、版本与对象存储、本地文档导入、模型提取与独立预审 | 任意游戏全网抓取、自动获得素材版权 |
| 趋势与选题 | 新闻 RSS/GDELT、可选 YouTube 免费配额接口、人工录入 TikTok 观察、可解释匹配与人工选择 | 新闻等于 TikTok 实时热度；匹配分等于营销效果 |
| 营销策划 | 本地模型生成具体建议，另一次模型调用独立检查 | 模型建议是已验证的市场结论 |
| 脚本与评审 | 本地模型写作 → 独立语义评审 + 确定性规则 → 限次修订；逐镜人工编辑 | 填满模板就完成创作；模型自批发布 |
| 恢复与审计 | 数据库任务、租约续期、取消、幂等、分阶段缓存、来源/版本/用量追踪 | 用日志代替业务结论；进程停止后仍继续执行 |
| 辅助工作区 | GDD 结构整理、账户/RBAC、备份恢复、诊断 | 已具备计费、平台投放归因或商业 SLA |

只有名称、厂商或类型标签时，会提示补充游戏内容，不会硬编玩法卖点。
旧“生成”接口保留为**手动脚手架**，界面明确标注；旧“自动修订”模板重置逻辑已停用。
旧版规则评测不能直接授权新版交付，需重新检查当前版本。

知识审核保留 M18 的项目级待办定位、下一条跳转、已提交折叠区和中英预设理由。
营销审核与脚本终审也显示明确的提交状态；只有主动更改决定才重新展开。
策划和脚本现在逐段列出模型判断、原句、引用事实；脚本可一键定位并选中待修改字段。
知识事实保留冻结实体名称和地区/版本范围；保存人工修改后，刷新不会再被旧模型任务带回旧稿。
GDD、运行记录和账户继续放在辅助工具层，不增加主创作步骤。

## 架构：5 个模型角色，3 个确定性工具角色

- 模型角色：Knowledge Curator、Knowledge Reviewer、Campaign Strategist、Script Writer、Quality Critic。
- 工具角色：来源与溯源、趋势清洗匹配、GDD 结构整理。
- Harness（工作流控制层）管理队列、权限、预算、重试、版本和人工关口，不是另一个聊天 Agent。
- 用结构化产物交接，不让多个 Agent 无限制互聊。创作采用有界“生成—检查—修订”，
  不把它包装成 ReAct、自学习或自主投放。

后端：Python/FastAPI/Pydantic、SQLAlchemy/Alembic、PostgreSQL 17/pgvector。
前端：React/TypeScript/Vite。模型：本机 Ollama，仅允许受控的本机地址，
**没有付费模型自动回退**。SQLite 只用于隔离测试，不是正式数据库替代方案。

详见 [系统架构与 DAG](docs/architecture/system-architecture.md)、
[产品基线](docs/product/baseline-v2.md)、[工作流说明](docs/product/real-creative-workflow.md)。

## 本地运行

前置环境：Python 3.12+、Node.js 22+、项目锁定版本的 pnpm、可运行 Linux 容器的 Docker。
在项目根目录打开 PowerShell：

```powershell
.\scripts\setup.ps1
.\scripts\database.ps1 up
.\.venv\Scripts\python.exe -m alembic upgrade head
.\scripts\start.ps1
```

开发入口默认是 [http://localhost:5173](http://localhost:5173)，API 默认是
[http://localhost:8000/health](http://localhost:8000/health)。
启动终端需要保持运行。重启后应先恢复数据库，再启动 API、worker 和前端。

```powershell
.\scripts\doctor.ps1
.\scripts\verify.ps1
```

模型名称与超时在 [.env.example](.env.example) 中说明。模型缺失或不可用时会禁用相应操作，
保留阅读、手动编辑和可解释规则，不会伪装成成功。模型选择必须做实际质量验证，
不能仅凭模型能下载或接口返回成功判断可用。

## 可重复验证

```powershell
# 常规检查；未配置 PostgreSQL 时，数据库专属测试会明确跳过
.\scripts\verify.ps1

# 可选：真实本地模型烟测。只用独立 SQLite 和标明来源的测试材料，不改个人项目
.\.venv\Scripts\python.exe scripts/creative_model_smoke.py --model qwen3.5:4b --revisions 2

# 重复评审正反例；逐次保留失败，任何误判或运行错误均非零退出
.\.venv\Scripts\python.exe scripts/creative_critic_smoke.py --model qwen3.5:9b --repeats 2
```

模型烟测记录实际模型、输入输出摘要、用量、耗时、评审和版本，但**不授予人工终审**。
退出码 `1` 表示任务失败，`2` 表示任务执行完但模型/规则质量门未通过；`0` 也只表示这些
自动检查通过，**仍需复读实际内容**，不代表通过人工内容验收。报告在被 Git 忽略的 `data/qa/` 中。

PostgreSQL 测试只可指向**独立测试库**；不能将生产或个人项目库设为测试 URL。
CI 使用带 pgvector 的 PostgreSQL，验证迁移、业务约束和前后端测试。

## 文档与边界

- [M19 实现、自查、验收步骤](docs/product/real-creative-workflow.md)
- [前端引导工作区](docs/product/guided-workspace.md)
- [完整本地能力验收矩阵](docs/product/acceptance-matrix-complete-local.md)
- [路线图](docs/roadmap.md)
- [安全说明](SECURITY.md) · [本地隐私边界](docs/security/local-development.md)
- [依赖锁定与更新](docs/security/reproducible-releases.md)
- [历史里程碑能力记录](docs/migration/m0-m18-feature-history.md)

账号、模型权重、原始资料、数据库、备份文件和密钥不上传 Git。
第三方素材使用权、活动规则、投放合规与最终创作判断仍需内容负责人确认。

## License

[MIT](LICENSE)。第三方模型和素材遵循各自许可。

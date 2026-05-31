# Local AI Support v3.1.2 第一阶段总结报告

## 1. 阶段结论
v3.1.2 第一阶段目标已完成，核心增量改造能力已按“最小影响、逐步接入、可观测优先”落地。

建议合并：是。

## 2. 测试结果
- `python3 -m compileall support_app app scripts`：通过
- `.venv/bin/python -m pytest -q`：`137 passed, 5 warnings`
- `node --check app/static/admin.js`：通过
- `node --check app/static/chat-v2.js`：通过
- failed 数量：0

## 3. 新增模块清单
- `RiskPolicyService`：纯规则风险识别服务，提供 `precheck/evaluate`，输出 `risk_level`、`need_human`、`route`、`safe_answer`、`risk_reasons` 等标准结构。
- `PostRuleCheckService`：纯规则后置检查服务，对回答进行承诺词、免责声明、handoff 语义、报价来源等合规检查。
- `ConversationStateStore`：独立会话状态存储（`data/conversation_state.json`），支持按 `channel:conversation_id` 隔离、TTL 过期、损坏兜底、原子写入。
- `UnderstandPlanAdapter`：薄适配层，聚合 `intent_plan/sales_plan/context_plan/conversation_state/risk_plan` 为统一 `understand_plan`。
- `CachePolicyMetadataService`：生成统一 `cache_policy_metadata`，仅做 observation 与行为差异评估，不直接改 RetrievalService。

## 4. 修改模块清单
- `ChatService`
  - 新增 blocked 风险前置拦截，确保在 identity/FAQ/DOC/quote/fallback 等早返回前可短路到 handoff。
  - 接入会话状态 observation：读取 `conversation_state_before`，返回后写入 `conversation_state_after`。
  - 接入最小 cache enforce：在上层将 `bypass_cache` 仅做 `false -> true` 升级。
- `AnswerPipeline`
  - 前置写入 `risk_precheck` metadata。
  - finalize 阶段接入 `post_rule_check` observation，并对 `blocked=true` 做最小 enforce。
  - 聚合写入 `understand_plan` 与 `cache_policy_metadata`。
  - 保持 metadata merge，不覆盖既有关键字段。
- `support_app/dependencies.py`
  - 增加风险、后置检查、状态存储、理解适配等依赖注入并挂载至服务。
- `data/agent_behavior_rules.json`
  - 新增 `risk_policy` 配置段（关键词、安全话术、回答边界）。
- 相关 tests
  - 补充 risk/post-rule/state/understand/cache-policy 及 pipeline/context 回归用例。

## 5. 已完成能力
- blocked 风险前置拦截
- blocked 后置 enforce
- high/medium observation
- conversation_state 独立存储
- conversation_state before/after metadata
- understand_plan metadata
- cache_policy_metadata
- 最小 bypass_cache enforce
- RetrievalService 本体未重构
- route / answer / need_human 最小影响原则

## 6. 当前 metadata 字段
- `risk_precheck`
- `risk_plan`
- `post_rule_check`
- `post_rule_enforce_applied`
- `original_answer`
- `original_route`
- `original_need_human`
- `conversation_state_before`
- `conversation_state_after`
- `understand_plan`
- `cache_policy_metadata`
- `cache_policy_enforce_applied`
- `original_bypass_cache`
- `final_bypass_cache`
- `decision_trace / sales_decision_trace`

## 7. 当前暂缓项
- `medium/high disclaimer enforce`：为避免一次性扩大回答改写面，阶段一仅 observation。
- `price_number_without_source enforce`：当前仅 warning，避免误伤现有报价表达路径。
- `quote_intent / quote_stage enforce`：当前仅 observation，待影子观测后再启用。
- `Streaming/SSE`：不属于第一阶段最小改造范围。
- `UnifiedUnderstand` 小模型版：阶段一优先复用现有规则服务，不引入新模型链路。
- `Qdrant collection` 分离：当前无必须性，暂不做数据面重构。
- `Reranker`：检索质量增强项，优先级低于安全与缓存治理主线。
- `Diagnostics` 前端面板：阶段一聚焦后端能力和 metadata 打通。

## 8. 已知不足
- 仍有 5 条 warnings。
- 场景 4/5/9/10 为部分覆盖。
- medium/high 当前仅 observation。
- quote_intent / quote_stage 当前仅 observation。
- cache_policy enforce 仍是 minimal 模式。

## 9. 合并前检查清单
- [x] 全量测试通过
- [x] route 枚举未新增
- [x] RetrievalService 本体未重构
- [x] conversation_history.json 未迁移
- [x] conversation_state.json 独立
- [x] 前端 JS 语法检查通过
- [x] 没有自动 push
- [x] 没有改 `.env`
- [x] 没有破坏旧 48 passed 基线

## 10. 下一阶段建议
1. 补端到端测试：pronoun/track、库存、交付
2. medium/high disclaimer enforce 灰度开关
3. quote_intent / quote_stage enforce 影子观测后再启用
4. Diagnostics 面板
5. UnifiedUnderstand 小模型版
6. Streaming/SSE
7. Retrieval metadata 增强

## 11. 建议 commit 拆分
- `risk-policy`: RiskPolicyService + 配置 + 风险测试
- `post-rule-check`: PostRuleCheckService + observation/enforce + 测试
- `conversation-state`: ConversationStateStore + Chat/metadata 接入 + 测试
- `understand-cache-metadata`: UnderstandPlanAdapter + CachePolicyMetadataService + pipeline 接入 + 测试
- `regression-tests`: context/pipeline 回归用例集中补强

## 最终建议
- 是否建议合并：是
- 合并风险等级：中
- 合并前必须人工确认的点：
  - blocked 命中后的客服话术是否满足业务合规与品牌语气要求
  - medium/high observation 升级 enforce 的触发阈值与灰度策略
  - 场景 4/5/9/10 的端到端补测范围与验收口径

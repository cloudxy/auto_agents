# ADR-0004: 数据库 36 表架构——软删除豁免矩阵 + 多态关联 + 通用工作流

日期：2026-09-02/03 · 状态：已实施（迁移 019/020/021/022/023，工单 DB-01~12 全 resolved）

## 决策

1. **软删除豁免矩阵**（SoftDeleteMixin.deleted_at，Repository 自动过滤）：
   业务主表加软删（12 表）；审计/历史/运行记录表（operation_logs/skill_reviews/skill_jobs/channel_*）
   不加；子表不加（级联跟随父表：llm_provider_models/capability_*）；聚合表不加（llm_token_usage）；
   系统表不加（tenants/users/system_configs——users 例外经 AdminUserAPI 走软删）。
2. **审计 Mixin**（created_by/updated_by String(64) 用户名）：与 TenantMixin 并列；
   spider_task_templates.created_by 由 Integer(用户id) 迁至 String(用户名)。
3. **多态关联统一约定**：tags/taggings/attachments/notifications/resource_versions/
   i18n_translations 均用 `resource_type + resource_id`（取值=模型名小写下划线）。
4. **通用工作流引擎**（4 表：definitions/instances/steps/transitions）：
   steps_config JSON 任意拓扑；transitions 挂 step 级（step_id NOT NULL），
   实例级流转由 status/started_at/completed_at 还原；状态机非法流转拒绝。
5. **FK 补全带孤儿清理回填**（迁移内先 DELETE 孤儿再建约束）；
   system_configs.utcnow → func.now()。

## 后果

- Repository 层 `hasattr(deleted_at)` 条件过滤，无 Mixin 表行为不变（向后兼容）
- 硬删除保留给确需场景（BaseRepository.delete）；软删行全链查询排除
  （llm_providers 的 list/get_by_name/get_active/resolve 均显式过滤）
- 后续扩展：restore 端点已具备（BaseRepository.restore），回收站 UI 未做

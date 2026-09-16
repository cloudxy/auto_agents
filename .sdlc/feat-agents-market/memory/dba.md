# dba 记忆 · feat-agents-market

## 交付（2026-09-15）
- 02-shape/db-spec.md + 02-shape/schema.dbml（check-sdlc --hat dba 过；db_ir.sh 全仓 exit 0）
- 结论：零新表、零新索引；仅 050 = capability_assets +featured(SmallInteger NOT NULL server_default "0") +examples(JSON NULL)。逐行规格在 db-spec §8，T-05 落地；实测 alembic head=049 单头（WIP 基底）。
- 返工 r1（QA-6 minor 已修）：db-spec §1 featured 列型散文统一 smallint 口径（原「tinyint（ORM SmallInteger）/MySQL 落 tinyint」与 §8 迁移规格、schema.dbml、DDL 实测三方矛盾）；schema.dbml 本就正确未动。教训：列型散文必须照抄 DDL 实测，勿凭 MySQL 布尔惯例想象；contract.md:162 的 tinyint(1) 属 architect 侧。

## 关键判定
- 导入两段式无 job 表（判型确定性，无强理由）；最热=installs 实时聚合（不落汇总列）。
- 零索引依据：货架过滤 93% 命中（EXPLAIN filtered=1.10 是低估），194 行(10x=2000) filesort 全内存；ANALYZE latest 0.587ms / hot 1.32ms。
- **AD-6 的 `NULLS LAST` 是 PG 语法，MySQL 报错（项目事故模式）**——已写 db-spec §9：sorting.py 必须 COALESCE(cnt,0) DESC。T-06 勿照抄 contract 原文。
- agents_hub._desired 白名单不含 featured/examples → 同步不重置治理字段；**T-07 树导入必须沿用「只 set desired 键」纪律**，否则每次同步清空精选/示例。

## 环境事实
- 本地 MySQL 8.0.42：mysql 客户端 /opt/homebrew/opt/mysql-client@8.0/bin/mysql；密码在 config/local/.env 的 AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD，值带引号需剥（Dynaconf 剥、shell 不剥）；用 MYSQL_PWD 传。
- information_schema 看不见 TEMPORARY 表——迁移可逆性验证用 CREATE TEMPORARY TABLE ... LIKE + SHOW COLUMNS（会话级，不碰 alembic_version）。
- dbml 门禁（tools/check/db_ir.sh）：R-ENUM 禁止 `status.*varchar` 同行（status 列用 enum 块）；R-AUD 每表须 created_at+updated_at；R-FK 至少一条 Ref。迁移门禁 SM-5：NOT NULL 加列必须 server_default。

## 开放问题（在案）
- featured/examples PATCH 触发 updated_at onupdate 跳变→顶进「最新」前排；默认接受，pm 可改语义（db-spec §10）。
- batch_id 应答生成不入库；要审计明细则落 product_events.props（operator，不阻塞）。

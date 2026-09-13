# frontend memory · feat-product-complete

> Facts this role learned (**what**). Procedures stay in SKILL.md (**how**). Cap **2200 chars**. Frozen snapshot for next spawn.

## Last

- Date: 2026-09-12
- Hat: sdlc-workflow:frontend（GWT-103.4 微票：FileTab 空态冻结句，verify 唯一缺口闭合）
- Outputs: T-40-evidence.md 追加补票节；spider jest 3 套件 10 测 exit 0（FileTab 6/6 含新空态测）；build exit 0；触碰文件 eslint 0 输出

## Facts

- **GWT-103.4**：采集方案 tab 空态三件套=主句「还没有采集方案。」+说明「创建入口在 AI 采集规划。」（Text secondary 次行）+次链 Button primary navigate('/ai')（edge-states 屏钉句；Empty CTA 形态照 Users.tsx PRESENTED_IMAGE_SIMPLE 先例）。FileTab 引入 useNavigate 后其测试 renderTab 必须包 MemoryRouter（TaskModal.test 同型），否则全部炸 hook 上下文。

- **T-11**：探针 tab 计数徽标（`probe-latest-batch` testid）数据源=overview `latest_batch_verdicts.spoofed`（权威，避免分页截断）；用与 Overview3q **同一 queryKey `['newapi','overview']`** 共享缓存零额外请求。overview 失败/无批次→徽标静默不渲染（不新增空态句）。冻句常量 PROBE_LATEST_BATCH_LABEL/PROBE_SPOOF_SUMMARY 入 newapiShared。总览 spoofed 置顶+计数「伪装: N」、租户 404 守卫=既有（T-32/T-29），只补断言。
- **zsh 管道吞退出码**：`cmd | tail` 后 `${PIPESTATUS[0]}` 在 zsh 不存在（小写 pipestatus）→ `$?` 取到 tail 的 0。取证用 `cmd > log 2>&1; ec=$?` 再 tail log。
- **F-7 排除 `*.test.tsx`**；测试文件跑 npx eslint 报既有 testing-library 规则错（不在 CI/gate 路径），新增断言沿用文件内 `closest('tr')` 既有模式即可；业务文件必须 0 输出。
- T-06：/outbound-keys=数据工厂组叶；写面 canManage∈{owner,admin,operator}（operator 可签发，与 relay 页不同）；菜单叶三角色都见→tenantOnly 单控即可。
- antd v6 两字按钮自动插空格→断言 `/禁\s*用/` 形态；Tag/多字文本不受影响。react-query v5 mutationFn 第二参带 {client,meta}。
- shared 改后 barrel index.ts 补导出+rebuild dist（P-FE-01）；Usage harness=真 useAuthStore.setState（须含 access_token/token_type/username/is_admin）。
- 全量 admin jest ~640s（35 套）；动共享 menuConfig/App.tsx 后必须全量回归。时间戳夹具用相对时刻（NOW-5min）防 24h 窗口掉出。

## Open (mine)

- EventsList 表零行走 antd 默认「暂无数据」（工单 80 既有；GWT-61.2 未走查事件 tab 空态）——已写 T-11 evidence §6 观察项，等 pm 定冻句。

## Do not re-litigate

- 官网渠道组句；T-31 页头；T-32「—」；T-34 横幅+保存并发布；T-28 两行；T-36 汇总；T-40 键集合固定；T-18 提交时校验；GWT-98.2 时间炸弹；T-20 只读降级；T-21 平台超管+owner/admin；T-23 钉句照抄+Tabs 保活喂行；T-03 页内 Tab+官网冻结+PRO 常量钉字面；T-06 tenantOnly 单控+互斥句唯一豁免+吊销确认弹窗；T-11 计数走 overview 权威口径+静默降级。

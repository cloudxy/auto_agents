# fix-checksdcc-exemptions · S 档（泳道：L1 · appetite：30min）

## 目标
check-sdlc.sh 对非流程工件（_lessons.md 账本/README/模板）误报 NOLANE 违规，
需豁免基础设施文件，只校验真正的任务工件。

## 验收标准
FR-01 Given .sdlc/ 目录含 _lessons.md When 跑 check-sdlc.sh .sdlc Then 退出码 0（无误报）
FR-02 Given 违规样例目录（spec 缺 GWT）When 跑 check-sdlc.sh Then 该违规仍被抓（无漏报）

## 状态转换推演
新增 EXEMPT 文件名集合；不改变既有规则语义（纯白名单收紧作用域）。

## 实现记录
scripts/check-sdlc.sh：新增 EXEMPT_RE 豁免集（_lessons.md / README.md / templates/），
find 结果过 grep -vE 过滤——基础设施文件不参与泳道/证据校验，只校验任务工件。

## 自测证据
FR-01（_lessons 误报消除；终态重录 2026-09-04）：
```
$ bash check-sdlc.sh <tmp>/.sdlc   # 密封夹具：仅 _lessons.md
check-sdlc: 无工件，跳过
exit code 0
```
FR-02（违规仍被抓，无漏报）：
```
$ bash ~/.zcode/local-plugins/sdlc-workflow/scripts/check-sdlc.sh /var/folders/fq/5l9p0spx3p977m5bk3746g9r0000gn/T/tmpyavjs8m6/spec.md
[0;31m✗ [SDLC-SUMMARY] 共 3 处违规[0m
exit code 4
```

## 审查 findings
（审查帽填）

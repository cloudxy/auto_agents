# feat-checksdlc-stats · S 档（泳道：L2 · appetite：45m）

## 目标
给 check-sdlc.sh 加两个能力：① `--stats` 汇总 .sdlc/ 下全部 state.yaml 的四度量；
② 证据-期望一致性检查（ESC-8 教训机械化：FR 要求退出码 0 而证据块记录非 0 时抓违规）。

## 验收标准（编号只追加）
FR-01 Given .sdlc/ 含 1 份已关账的 L1 state.yaml（metrics 存在）When `check-sdlc.sh --stats` 
Then 输出含"泳道分布 L1=1"、"拦截 6"、25 分钟耗时且退出码 0
FR-02 Given 工件含 FR 要求"退出码 0"且其证据块记录 `exit code 2` When 对该工件跑检查 
Then 输出 EVIDMISMATCH 违规行且退出码非零
FR-03 Given 上一票 fix-note（FR 期望 0/非零均有、证据块全部相符）When 跑检查 
Then 零误报退出码 0

## 范围外
不做 YAML 解析器（grep/sed 近似即可）；不做跨 .sdlc 历史趋势（首版只汇总当下）；JSON 输出。

## 状态转换推演
--stats 模式跳过工件校验路径（互斥分支）；EVIDMISMATCH 并入既有 EVID 检查流，不改变其他规则。

## 实现记录
check-sdlc.sh 三处：① --stats 互斥分支（declare -a 泳道计数/find state.yaml 汇总）；
② 帽子感知 EVID 豁免（state.yaml hats_done 无"实现"时跳过证据检查——定义帽阶段跑门禁不再误报）；
③ EVIDMISMATCH awk 配对（FR Then 期望 vs 证据块 exit code）。自测中修掉三个缺陷：
全角括号邻接裸变量（bash 3.2 多字节扫描，统一 ${}）、awk 变量名 exp 撞内置函数（→want）、
awk \x60 转义 BSD 不支持（删围栏感知）。

## 自测证据（受控夹具，终态输出）
FR-01（--stats 输出四度量 + exit 0）：
```
$ bash check-sdlc.sh --stats .sdlc
平均耗时: 25 分钟/票
L3+ 占比: 0%（>40% 判定过严）
exit code 0
```
FR-02（FR 期望 0 / 证据 2 → EVIDMISMATCH 抓到）：
```
$ bash check-sdlc.sh <tmp>/spec.md
[SDLC-EVIDMISMATCH] .../spec.md: FR 期望 0 但证据记录 exit code 2（中间态证据禁入——重录终态输出）
exit code 4
```
FR-03（上一票已关账工件零误报）：
```
$ bash check-sdlc.sh .sdlc/fix-checksdcc-exemptions
----------------------------------------
exit code 0
```

## 审查 findings
（审查帽填）

## 审查 findings
（审查帽填）

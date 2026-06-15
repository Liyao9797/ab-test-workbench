# Local A/B Test Workbench Test Plan

## 一. 测试目标

验证本地 A/B 测试分析工作台可以稳定完成核心流程：

```text
启动服务 -> 上传 Excel 或生成 demo -> 识别表头 -> 选择字段 -> 执行分析 -> 生成图表 -> 下载结果
```

重点验证：

- Excel 上传和表头识别正确。
- 字段选择校验有效。
- Stage 2 分析结果正确展示。
- Stage 3 图表只读取 Stage 2 结果，不重新计算显著性。
- Gate 和 WARNING 表达正确。
- 图表数量上限为 7。
- 运行产物写入 `storage/`，且不进入 Git。

## 二. 测试范围

本期测试范围：

- 前端页面主流程。
- 后端 API。
- Excel 上传和 demo 生成。
- 表头识别。
- 二元指标、连续指标和类别指标分析。
- Gate / WARNING。
- Stage 2 workbook 和 JSON 输出。
- 图表生成和 manifest。
- 下载链接和图表预览。

暂不测试：

- 登录权限。
- 多用户协作。
- 在线数据库。
- 外部 issue 系统。
- 多组实验完整事后检验。
- 页面内图表编辑。

## 三. 测试环境

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## 四. 核心测试用例

### 4.1 健康检查

步骤：

1. 启动后端。
2. 请求 `/api/health`。

预期：

- 返回 `ok=true`。
- 返回版本号。

### 4.2 前端加载

步骤：

1. 启动前端。
2. 打开首页。

预期：

- 页面正常渲染。
- API 状态显示正确。
- 未上传文件时，分析按钮不可用。

### 4.3 Excel 上传

步骤：

1. 上传有效 `.xlsx` 文件。
2. 查看页面文件状态。

预期：

- 返回 `upload_id`。
- 文件保存到 `storage/uploads/{upload_id}/original.xlsx`。
- 写入 `metadata.json`。
- 页面显示文件名、sheet 和字段配置入口。

### 4.4 非法文件上传

步骤：

1. 上传非 `.xlsx` / `.xlsm` 文件。

预期：

- 后端返回 400。
- 前端显示清晰错误。
- 不生成有效 upload 记录。

### 4.5 demo 数据生成

步骤：

1. 点击生成卡方 demo。
2. 查看 sheet 和字段识别结果。

预期：

- 返回 `chi_square_demo_ab_test.xlsx`。
- 默认 sheet 为 `chi_square_demo`。
- 字段包含 `group_id`、`outcome_category`、`feature_clicked`、`login_days` 等。
- 自动选择合理的默认分组字段和部分指标字段。

### 4.6 表头识别

步骤：

1. 对已上传文件执行表头识别。
2. 查看字段列表和样例值。

预期：

- 返回 `detected_header_row`。
- 返回字段名、索引、类型和样例值。
- 返回预览数据。
- 写入 `detected_headers.json`。

### 4.7 sheet 切换

步骤：

1. 上传包含多个 sheet 的 workbook。
2. 切换 sheet。

预期：

- 清空旧字段选择。
- 对新 sheet 重新识别表头。
- 清空旧分析结果和旧图表状态。

### 4.8 字段选择校验

步骤：

1. 不选择分组字段。
2. 不选择指标字段。
3. 选择超过 5 个指标字段。
4. 选择分组字段作为指标字段。

预期：

- 前三种情况不能执行分析。
- 后端拒绝字段重叠请求。
- 错误信息能说明原因。

### 4.9 标准二元指标分析

步骤：

1. 上传标准 A/B Excel。
2. 选择 `group_id` 作为分组字段。
3. 选择二元指标，例如 `feature_clicked`。
4. 执行分析。

预期：

- 返回 `job_id`。
- Gate 为 `PASS` 或 `PASS_WITH_WARNING`。
- 生成 `stage2_result.xlsx`。
- 生成 `stage2_result.json`。
- 结果包含 A/B 值、差异、相对提升、p 值、95% CI 和显著性。
- 页面展示 PM 可读结论。

### 4.10 连续指标分析

步骤：

1. 选择连续数值指标，例如 `login_days`。
2. 执行分析。

预期：

- 使用均值差异检验。
- 输出 A/B 均值、差异、p 值和 95% CI。
- 可生成对应指标图。

### 4.11 类别指标分析

步骤：

1. 使用 demo 数据。
2. 选择类别指标，例如 `outcome_category`。
3. 执行分析。

预期：

- 使用卡方检验。
- 输出列联表、卡方统计量、自由度和 p 值。
- 可生成类别分布图。

### 4.12 PASS_WITH_WARNING

步骤：

1. 使用样本不均衡或字段风险数据。
2. 执行分析。

预期：

- Gate 为 `PASS_WITH_WARNING`。
- 页面高亮 WARNING。
- 仍允许生成图表。
- PM 结论包含风险提示。

### 4.13 FAIL 阻断出图

步骤：

1. 使用分组字段超过两组的数据。
2. 执行分析。

预期：

- Gate 为 `FAIL` 或后端返回明确错误。
- 页面禁止生成图表。
- 错误提示说明第一版仅支持两组对比。

### 4.14 Stage 3 图表生成

步骤：

1. 完成一次有效 Stage 2 分析。
2. 点击生成图表。

预期：

- 每个可出图指标生成 1 张指标图。
- 生成 `summary.png`。
- 生成 `complete_all_charts.png`。
- 写入 `manifest.json`。
- `chart_count <= 7`。
- 页面可以预览图表。

### 4.15 Stage 3 不重新计算显著性

步骤：

1. 记录 Stage 2 workbook 中的 p 值和置信区间。
2. 生成图表。
3. 查看图表详情或 manifest。

预期：

- 图表读取 Stage 2 workbook。
- 不产生新的 p 值计算。
- 图表展示值与 Stage 2 一致。

### 4.16 图表文件访问安全

步骤：

1. 请求 `/api/charts/{job_id}/../secret`。
2. 请求包含 `/` 的 filename。

预期：

- 返回 400。
- 不读取 chart 目录外文件。

### 4.17 运行产物忽略

步骤：

1. 完成上传、分析和出图。
2. 查看 `git status --short`。

预期：

- `storage/` 不出现在待提交文件里。
- `.venv`、`node_modules`、`dist`、`__pycache__` 不出现在待提交文件里。

## 五. 回归样例

### 5.1 标准显著样例

输入：

- A/B 各 400 人。
- `feature_penetration_rate` A=50%，B=60%。

预期：

- p 值约为 `0.004474`。
- 95% CI 约为 `[+3.14pp, +16.86pp]`。
- 结论为显著。

### 5.2 低提升不显著样例

输入：

- A/B 各 400 人。
- `feature_penetration_rate` 约 A=51%，B=57.5%。

预期：

- p 值约为 `0.065015`。
- 95% CI 包含 0。
- 结论为方向正向但证据不足。

### 5.3 类别分布差异样例

输入：

- demo workbook。
- `group_id` 作为分组。
- `outcome_category` 作为类别指标。

预期：

- 生成卡方检验结果。
- 输出列联表。
- 图表展示不同组的类别分布。

## 六. 验收标准

v1 可验收条件：

- 页面能完成上传、识别、选择字段、分析、出图和下载。
- demo 数据可一键生成并跑通核心流程。
- Stage 2 结果能稳定展示。
- Stage 3 图表能稳定预览。
- 图表数量限制生效。
- `PASS` / `PASS_WITH_WARNING` / `FAIL` 行为正确。
- 标准显著样例、低提升不显著样例和类别分布样例均符合预期。
- README、PRD、技术说明和测试计划与当前代码一致。

## 七. 当前测试缺口

后续建议补充：

- 后端单元测试。
- API 集成测试。
- 前端构建验证。
- 浏览器端到端测试。
- 图表像素级或文件存在性验证。
- 问题上报功能恢复后的报告生成测试。

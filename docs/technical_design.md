# Local A/B Test Workbench Technical Design

## 一. 设计目标

实现一个本地 Web 工作台，前端负责用户配置和结果展示，后端负责 Excel 解析、实验分析、文件管理和图表生成。

核心设计目标：

- 单页完成上传、字段识别、分析、出图和下载。
- 后端以本地文件系统保存上传、分析结果和图表。
- Stage 3 图表生成只读取 Stage 2 输出，不重新计算显著性。
- 代码结构简单，适合个人项目展示和后续扩展。

## 二. 技术栈

- 前端：React 19、TypeScript、Vite、lucide-react。
- 后端：FastAPI、Pydantic、pandas、openpyxl、Pillow。
- 存储：本地 `storage/` 目录。
- 文件输入：`.xlsx`、`.xlsm`。
- 图表输出：PNG 和 JSON manifest。

## 三. 当前目录结构

```text
.
  README.md
  docs/
    prd.md
    technical_design.md
    test_plan.md
    superpowers/specs/
  frontend/
    package.json
    vite.config.ts
    index.html
    src/
      main.tsx
      styles.css
  backend/
    requirements.txt
    main.py
    app/
      api/
        routes_health.py
        routes_upload.py
        routes_analysis.py
        routes_charts.py
      core/
        paths.py
      schemas/
        upload.py
        analysis.py
      services/
        excel_service.py
        analysis_service.py
        chart_service.py
      adapters/
        analyze_ab_test_adapter.py
  ab-test-workbench-mvp-no-anova/
    PACKAGING_NOTES.md
    ...
```

说明：

- 根目录代码是当前主要版本。
- `ab-test-workbench-mvp-no-anova/` 是历史打包目录，包含部分 report 相关实现，后续可选择合并或移除。
- `storage/` 为运行时目录，已被 `.gitignore` 忽略。

## 四. 系统架构

```text
React Dashboard
  |
  | HTTP /api
  v
FastAPI backend
  |
  +-- excel_service.py      上传保存、sheet 读取、表头识别、demo 生成
  +-- analysis_service.py   质量 Gate、显著性分析、workbook 和 JSON 输出
  +-- chart_service.py      从 Stage 2 workbook 生成 PNG 图表和 manifest
  |
  v
storage/
  uploads/
  jobs/
  results/
  charts/
```

## 五. 前端设计

当前前端为单文件主应用：

```text
frontend/src/main.tsx
frontend/src/styles.css
```

主要状态：

- API 在线状态。
- 上传文件元信息。
- 表头识别结果。
- 当前 sheet。
- 分组字段。
- 指标字段。
- 可选分层字段。
- 分析结果。
- 图表结果。
- 错误和复制链接状态。

主要交互：

- 上传 Excel。
- 生成卡方 demo 数据。
- 切换 sheet 并重新识别表头。
- 选择 1 个分组字段。
- 选择 1 到 5 个指标字段。
- 选择 0 到 2 个分层字段。
- 执行分析。
- 生成图表。
- 查看统计表、PM 结论和图表预览。
- 复制 workbook 或图表链接。

当前前端为作品集和 MVP 优先，因此没有拆分组件。后续如果继续扩展，建议拆为：

- `components/upload`
- `components/field-picker`
- `components/analysis-result`
- `components/charts`
- `api/client`
- `types`

## 六. 后端设计

### 6.1 应用入口

`backend/main.py` 创建 FastAPI app，注册：

- `/api/health`
- `/api/uploads`
- `/api/analysis`
- `/api/analysis/jobs/{job_id}/generate-charts`
- `/api/charts/{job_id}/{filename}`

启动时调用 `ensure_storage_dirs()` 创建本地运行目录。

### 6.2 本地路径

`app/core/paths.py` 管理 `STORAGE_ROOT` 和运行目录。

建议运行期目录：

```text
storage/
  uploads/{upload_id}/
    original.xlsx
    metadata.json
    detected_headers.json
  jobs/{job_id}/
    request.json
    status.json
  results/{job_id}/
    stage2_result.xlsx
    stage2_result.json
  charts/{job_id}/
    metric_*.png
    summary.png
    complete_all_charts.png
    manifest.json
```

### 6.3 Excel 服务

`excel_service.py` 负责：

- 校验上传文件。
- 保存原始 Excel。
- 读取 sheet 列表。
- 自动识别表头行。
- 标准化字段名。
- 猜测字段类型。
- 生成预览数据。
- 生成卡方 demo workbook。

表头识别规则：

- 优先使用请求中的 `header_row`。
- 否则扫描前 10 行，选择第一个包含至少 2 个非空单元格的行。
- 如果没有明显表头，回退到第 1 行。

字段名规则：

- 空字段使用 `column_{index}`。
- 去除首尾空格。
- 中间空白替换为 `_`。

### 6.4 分析服务

`analysis_service.py` 负责：

- 校验用户选择的字段存在。
- 校验分组字段和指标字段不重叠。
- 校验分层字段和指标字段不重叠。
- 生成 `job_id`。
- 写入请求和状态文件。
- 生成质量 Gate。
- 计算样本量表。
- 计算指标检验表。
- 生成观察指标、分层诊断和 PM 结论。
- 输出 Stage 2 workbook 和结构化 JSON。

支持指标：

- `binary`：两样本比例检验。
- `number`：均值差异检验。
- `categorical`：卡方检验。
- `unsupported`：标记不可计算。

Gate 逻辑：

- 分组字段必须存在。
- 第一版必须恰好有两组。
- 每组样本必须非空。
- 样本不均衡等风险生成 WARNING。
- 任一 FAIL 导致总体 Gate 为 `FAIL`。
- 无 FAIL 但有 WARNING 时总体 Gate 为 `PASS_WITH_WARNING`。

### 6.5 图表服务

`chart_service.py` 负责：

- 从 `storage/results/{job_id}/stage2_result.xlsx` 读取 `primary_metric_test` sheet。
- 过滤不可出图指标。
- 为每个可出图指标生成 PNG。
- 生成汇总图 `summary.png`。
- 生成完整图表合集 `complete_all_charts.png`。
- 写入 `manifest.json`。

图表上限：

- 最多 5 个指标图。
- 1 张汇总图。
- 1 张完整合集图。
- 当前 manifest 的 `max_chart_count` 为 7。

## 七. API 设计

### 7.1 健康检查

`GET /api/health`

返回：

```json
{
  "ok": true,
  "version": "0.1.0"
}
```

### 7.2 上传 Excel

`POST /api/uploads`

请求：`multipart/form-data`

字段：

- `file`：`.xlsx` 或 `.xlsm` 文件。

返回：

```json
{
  "upload_id": "upl_xxx",
  "filename": "ab_test.xlsx",
  "file_size": 123456,
  "sheets": ["Sheet1"],
  "selected_sheet": "Sheet1",
  "path": "storage/uploads/upl_xxx/original.xlsx"
}
```

错误：

- 400：缺少文件名。
- 400：不支持的文件类型。
- 400：workbook 没有 sheet。
- 500：保存失败。

### 7.3 生成 demo 上传

`POST /api/uploads/demo/chi-square`

返回格式同上传接口，文件名为 `chi_square_demo_ab_test.xlsx`。

### 7.4 识别表头

`POST /api/uploads/{upload_id}/detect-headers`

请求：

```json
{
  "sheet_name": "Sheet1",
  "header_row": null,
  "preview_rows": 20
}
```

返回：

```json
{
  "upload_id": "upl_xxx",
  "sheet_name": "Sheet1",
  "detected_header_row": 1,
  "columns": [
    {
      "name": "group_id",
      "index": 0,
      "dtype": "string",
      "sample_values": ["group_a", "group_b"]
    }
  ],
  "row_count": 800,
  "preview": []
}
```

### 7.5 创建分析任务

`POST /api/analysis/jobs`

请求：

```json
{
  "upload_id": "upl_xxx",
  "sheet_name": "Sheet1",
  "group_field": "group_id",
  "metric_fields": ["feature_clicked"],
  "anova_factor_fields": ["platform"]
}
```

当前接口同步执行分析，直接返回完整分析结果：

```json
{
  "job_id": "job_xxx",
  "status": "completed",
  "gate_status": "PASS",
  "output_path": "storage/results/job_xxx/stage2_result.xlsx",
  "workbook_url": "/api/analysis/jobs/job_xxx/workbook",
  "requested_group_field": "group_id",
  "requested_metric_fields": ["feature_clicked"],
  "warnings": [],
  "pm_conclusion": "...",
  "tables": {}
}
```

### 7.6 下载分析 workbook

`GET /api/analysis/jobs/{job_id}/workbook`

返回 `stage2_result.xlsx`。

### 7.7 生成图表

`POST /api/analysis/jobs/{job_id}/generate-charts`

返回：

```json
{
  "job_id": "job_xxx",
  "chart_count": 3,
  "max_chart_count": 7,
  "skipped_metrics": [],
  "charts": [
    {
      "chart_id": "metric_1",
      "type": "metric",
      "metric": "feature_clicked",
      "url": "/api/charts/job_xxx/metric_1_feature_clicked.png",
      "filename": "metric_1_feature_clicked.png"
    }
  ]
}
```

### 7.8 获取图表 manifest

`GET /api/analysis/jobs/{job_id}/charts`

当前返回 manifest 地址：

```json
{
  "job_id": "job_xxx",
  "manifest_url": "/api/charts/job_xxx/manifest.json"
}
```

### 7.9 获取图表或 manifest 文件

`GET /api/charts/{job_id}/{filename}`

返回 PNG 或 JSON 文件。

安全限制：

- `filename` 不能包含 `/`。
- `filename` 不能包含 `..`。

## 八. 错误处理

后端错误通过 FastAPI `HTTPException` 返回：

- 400：用户输入或字段选择不合法。
- 404：上传、workbook 或图表不存在。
- 500：保存文件或分析执行失败。

前端需要把错误显示在页面主操作区附近，并清理正在进行的 loading 状态。

## 九. 当前实现与规划差异

当前已实现：

- 上传、demo、表头识别、分析、workbook 下载、图表生成、图表访问。

尚未在根目录主版本实现：

- `/api/reports` 问题上报接口。
- 异步任务队列和轮询。
- 拆分式前端组件结构。
- 统一 API client 和类型目录。

历史打包目录中存在 report 相关文件，可在后续整理时决定是否合并到主版本。

## 十. 后续扩展建议

- 合并或移除 `ab-test-workbench-mvp-no-anova/` 历史目录。
- 将 `frontend/src/main.tsx` 拆分为组件和 API client。
- 补齐问题上报能力。
- 为后端服务增加单元测试。
- 为核心流程增加端到端测试。
- 在 README 中加入截图和示例数据说明。

# Demo and Deployment Guide

## 一. 推荐展示策略

当前推荐策略是：**源码仓库 + README 截图 + 本地 demo**。

原因：

- 项目包含 FastAPI 后端，需要处理 Excel 上传、分析任务、workbook 下载和 PNG 图表生成。
- 项目默认使用本地 `storage/` 保存上传文件和运行结果，适合隐私数据和离线分析场景。
- GitHub Pages 只能托管静态前端，无法运行 FastAPI 后端和本地文件写入流程。
- 对简历展示来说，当前最有价值的是让读者看到产品定位、界面截图、技术结构和可本地跑通的完整链路。

因此，v1 不建议包装成“纯前端在线 Demo”。如果需要在线演示，应单独部署后端，并处理文件存储、跨域和数据清理策略。

## 二. 面试或作品集演示路径

推荐 5 分钟演示顺序：

1. 打开 README，先展示项目定位和示例图表。
2. 启动后端和前端。
3. 打开页面，确认右上角显示 `API 已连接`。
4. 点击 `生成 demo`，自动生成示例 Excel 并识别字段。
5. 确认分组字段和指标字段。
6. 点击 `Step 2 分析 Excel`。
7. 讲解 Gate、显著指标数、p 值、置信区间和 PM 可读结论。
8. 点击 `Step 3 生成图表`。
9. 打开图表预览，展示指标图、汇总图和完整图表合集。
10. 说明结果文件会落在本地 `storage/`，但该目录不会进入 Git。

## 三. 本地演示命令

### 1. 后端

建议使用 Python 3.10+。

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

预期返回：

```json
{
  "ok": true,
  "version": "0.1.0",
  "service": "local-ab-test-workbench"
}
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 四. 可选验证命令

前端构建：

```bash
cd frontend
npm run build
```

后端核心链路可通过页面验证，也可以用以下 API 顺序手动验证：

```bash
curl -X POST http://127.0.0.1:8000/api/uploads/demo/chi-square
```

拿到 `upload_id` 后：

```bash
curl -X POST http://127.0.0.1:8000/api/uploads/{upload_id}/detect-headers \
  -H 'Content-Type: application/json' \
  -d '{"sheet_name":"chi_square_demo","header_row":null,"preview_rows":5}'
```

执行分析：

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "upload_id":"{upload_id}",
    "sheet_name":"chi_square_demo",
    "group_field":"group_id",
    "metric_fields":["feature_clicked","outcome_category","login_days"],
    "anova_factor_fields":["platform"]
  }'
```

拿到 `job_id` 后：

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/jobs/{job_id}/generate-charts
```

## 五. 线上部署选项

### 方案 A：保持本地演示

适合当前 v1。

优点：

- 数据不离开本机。
- 最贴合项目的“本地分析工作台”定位。
- 部署成本低，适合作品集和面试现场演示。

限制：

- GitHub 页面不能直接在线体验完整流程。
- 读者需要本地安装 Node.js 和 Python。

### 方案 B：前后端分别部署

可选后续方案：

- 前端部署到 Vercel、Netlify 或 GitHub Pages。
- 后端部署到 Render、Railway、Fly.io 或自有服务器。
- 将 `apiBase` 改成环境变量。
- 使用云端临时文件存储或对象存储。
- 设置上传文件大小限制、定时清理和跨域白名单。

适合想要公开在线 Demo 的版本。

### 方案 C：Docker Compose

可选后续方案：

- 为后端创建 Dockerfile。
- 为前端创建生产构建和静态服务配置。
- 用 `docker-compose.yml` 同时启动前端、后端和挂载的 `storage/`。

适合降低本地环境差异，让面试官一条命令启动。

## 六. 当前不做的部署能力

v1 不包含：

- 登录和权限。
- 多用户隔离。
- 在线数据库。
- 外部对象存储。
- 自动清理上传文件。
- 在线公开 Demo 地址。

这些能力会显著扩大工程范围，当前更适合放进后续计划。

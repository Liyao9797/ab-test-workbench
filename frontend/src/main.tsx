import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bug,
  ChevronLeft,
  ChevronRight,
  X,
  Copy,
  FileSpreadsheet,
  FlaskConical,
  Image,
  Link,
  LineChart,
  Upload
} from "lucide-react";
import "./styles.css";

type UploadResponse = {
  upload_id: string;
  filename: string;
  file_size: number;
  sheets: string[];
  selected_sheet: string;
};

type ColumnInfo = {
  name: string;
  index: number;
  dtype: "binary" | "number" | "string" | "empty";
  sample_values: Array<string | number | boolean | null>;
};

type HeaderDetection = {
  upload_id: string;
  sheet_name: string;
  detected_header_row: number;
  columns: ColumnInfo[];
  row_count: number;
  preview: Record<string, unknown>[];
};

type AnalysisResult = {
  job_id: string;
  gate_status: string;
  output_path: string;
  workbook_url: string;
  requested_group_field: string;
  requested_metric_fields: string[];
  requested_anova_factor_fields?: string[];
  warnings: Array<{ check: string; detail: string }>;
  primary_metric: Record<string, string | number>;
  pm_conclusion: string;
  tables: {
    data_quality_check: Array<Record<string, string | number>>;
    sample_size: Array<Record<string, string | number>>;
    primary_metric_test: Array<Record<string, string | number>>;
    anova_tests?: Array<Record<string, string | number>>;
    observation_metrics: Array<Record<string, string | number>>;
    segment_diagnostics: Array<Record<string, string | number>>;
  };
};

type ChartResult = {
  job_id: string;
  chart_count: number;
  max_chart_count: number;
  skipped_metrics?: Array<{ metric: string; reason: string }>;
  charts: Array<{
    chart_id: string;
    type: string;
    metric: string | null;
    url: string;
    filename: string;
  }>;
};

const apiBase = "/api";

const resultRows = [
  ["Step 1", "上传或生成 demo", "读取 sheet、表头、字段类型和样例值"],
  ["Step 2", "选择分组与指标", "支持二元、连续数值和类别指标"],
  ["Step 3", "执行分析", "输出 Gate、p 值、置信区间和 PM 结论"],
  ["Step 4", "生成图表", "最多 5 张指标图 + 汇总图 + 完整图"]
];

const workflowCards = [
  ["导入", "Excel / Demo"],
  ["识别", "Sheet / Header"],
  ["分析", "Gate / p-value"],
  ["沉淀", "Workbook / Charts"]
];

function App() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [apiOnline, setApiOnline] = useState(false);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [headers, setHeaders] = useState<HeaderDetection | null>(null);
  const [selectedSheet, setSelectedSheet] = useState("");
  const [groupField, setGroupField] = useState("");
  const [anovaFactorFields, setAnovaFactorFields] = useState<string[]>([]);
  const [metricFields, setMetricFields] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isGeneratingDemo, setIsGeneratingDemo] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isPlotting, setIsPlotting] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [charts, setCharts] = useState<ChartResult | null>(null);
  const [selectedChart, setSelectedChart] = useState<ChartResult["charts"][number] | null>(null);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [chartCopyStatus, setChartCopyStatus] = useState("");

  useEffect(() => {
    fetch(`${apiBase}/health`)
      .then((response) => setApiOnline(response.ok))
      .catch(() => setApiOnline(false));
  }, []);

  const statusItems = useMemo(
    () => [
      { label: "当前文件", value: upload?.filename ?? "未上传", tone: upload ? "ready" : "idle" },
      { label: "分析状态", value: isAnalyzing ? "分析中" : analysis ? "分析完成" : "未分析", tone: analysis ? "ready" : "idle" },
      { label: "图表状态", value: isPlotting ? "生成中" : charts ? "生成完成" : "未生成", tone: charts ? "ready" : "idle" },
      { label: "Gate", value: analysis?.gate_status ?? "待检查", tone: analysis?.gate_status === "PASS" ? "ready" : analysis ? "warn" : "idle" }
    ],
    [analysis, charts, isAnalyzing, isPlotting, upload]
  );

  const canAnalyze = Boolean(upload && headers && groupField && metricFields.length > 0 && metricFields.length <= 5);
  const canPlot = Boolean(analysis && analysis.gate_status !== "FAIL");

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setError("");
    setUpload(null);
    setHeaders(null);
    setGroupField("");
    setAnovaFactorFields([]);
    setMetricFields([]);
    setAnalysis(null);
    setCharts(null);
    setSelectedChart(null);
    setCopyStatus("");
    setChartCopyStatus("");

    try {
      const formData = new FormData();
      formData.append("file", file);
      const uploadResponse = await fetch(`${apiBase}/uploads`, {
        method: "POST",
        body: formData
      });
      if (!uploadResponse.ok) throw new Error(await readError(uploadResponse));
      const uploadPayload = (await uploadResponse.json()) as UploadResponse;
      setUpload(uploadPayload);
      setSelectedSheet(uploadPayload.selected_sheet);

      const headerPayload = await detectHeaders(uploadPayload.upload_id, uploadPayload.selected_sheet);
      setHeaders(headerPayload);
      setGroupField(defaultGroupField(headerPayload));
      setAnovaFactorFields([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "上传失败");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleGenerateChiSquareDemo() {
    setIsGeneratingDemo(true);
    setError("");
    setUpload(null);
    setHeaders(null);
    setGroupField("");
    setAnovaFactorFields([]);
    setMetricFields([]);
    setAnalysis(null);
    setCharts(null);
    setSelectedChart(null);
    setCopyStatus("");
    setChartCopyStatus("");

    try {
      const response = await fetch(`${apiBase}/uploads/demo/chi-square`, { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const demoUpload = (await response.json()) as UploadResponse;
      setUpload(demoUpload);
      setSelectedSheet(demoUpload.selected_sheet);
      const headerPayload = await detectHeaders(demoUpload.upload_id, demoUpload.selected_sheet);
      setHeaders(headerPayload);
      setGroupField(defaultGroupField(headerPayload));
      setMetricFields(defaultChiSquareMetrics(headerPayload));
      setAnovaFactorFields([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成卡方检验样例失败");
    } finally {
      setIsGeneratingDemo(false);
    }
  }

  async function handleSheetChange(nextSheet: string) {
    if (!upload) return;
    setSelectedSheet(nextSheet);
    setHeaders(null);
    setGroupField("");
    setAnovaFactorFields([]);
    setMetricFields([]);
    setAnalysis(null);
    setCharts(null);
    setSelectedChart(null);
    setCopyStatus("");
    setChartCopyStatus("");
    setError("");
    try {
      const headerPayload = await detectHeaders(upload.upload_id, nextSheet);
      setHeaders(headerPayload);
      setGroupField(defaultGroupField(headerPayload));
      setAnovaFactorFields([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "表头识别失败");
    }
  }

  function toggleMetric(fieldName: string) {
    setMetricFields((current) => {
      if (current.includes(fieldName)) return current.filter((field) => field !== fieldName);
      if (current.length >= 5) return current;
      return [...current, fieldName];
    });
  }

  function toggleAnovaFactor(fieldName: string) {
    setAnovaFactorFields((current) => {
      if (current.includes(fieldName)) return current.filter((field) => field !== fieldName);
      if (current.length >= 2) return current;
      return [...current, fieldName];
    });
  }

  async function handleAnalyze() {
    if (!upload || !selectedSheet || !groupField || metricFields.length === 0) return;
    const orderedMetrics = orderMetricsBySheet(headers, metricFields);
    setIsAnalyzing(true);
    setAnalysis(null);
    setCharts(null);
    setSelectedChart(null);
    setChartCopyStatus("");
    setError("");
    try {
      const response = await fetch(`${apiBase}/analysis/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_id: upload.upload_id,
          sheet_name: selectedSheet,
          group_field: groupField,
          metric_fields: orderedMetrics,
          anova_factor_fields: orderMetricsBySheet(headers, anovaFactorFields)
        })
      });
      if (!response.ok) throw new Error(await readError(response));
      setAnalysis((await response.json()) as AnalysisResult);
      setCopyStatus("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "分析失败");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleGenerateCharts() {
    if (!analysis) return;
    setIsPlotting(true);
    setError("");
    setCharts(null);
    try {
      const response = await fetch(`${apiBase}/analysis/jobs/${analysis.job_id}/generate-charts`, {
        method: "POST"
      });
      if (!response.ok) throw new Error(await readError(response));
      setCharts((await response.json()) as ChartResult);
      setChartCopyStatus("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "图表生成失败");
    } finally {
      setIsPlotting(false);
    }
  }

  useEffect(() => {
    if (!selectedChart) return;
    function handleLightboxKeys(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedChart(null);
      if (event.key === "ArrowLeft") moveSelectedChart(-1);
      if (event.key === "ArrowRight") moveSelectedChart(1);
    }
    window.addEventListener("keydown", handleLightboxKeys);
    return () => window.removeEventListener("keydown", handleLightboxKeys);
  }, [selectedChart, charts]);

  function moveSelectedChart(direction: -1 | 1) {
    if (!charts || !selectedChart || charts.charts.length <= 1) return;
    const currentIndex = charts.charts.findIndex((chart) => chart.chart_id === selectedChart.chart_id);
    if (currentIndex < 0) return;
    const nextIndex = (currentIndex + direction + charts.charts.length) % charts.charts.length;
    setSelectedChart(charts.charts[nextIndex]);
  }

  async function handleCopyAnalysisTable() {
    if (!analysis) return;
    try {
      await navigator.clipboard.writeText(buildAnalysisTableText(analysis));
      setCopyStatus("已复制");
      window.setTimeout(() => setCopyStatus(""), 1800);
    } catch {
      setCopyStatus("复制失败");
    }
  }

  async function handleCopyChartPath(chart: ChartResult["charts"][number]) {
    try {
      await navigator.clipboard.writeText(new URL(chart.url, window.location.origin).href);
      setChartCopyStatus(`${chart.metric ?? "summary"} 路径已复制`);
      window.setTimeout(() => setChartCopyStatus(""), 1800);
    } catch {
      setChartCopyStatus("复制路径失败");
    }
  }

  async function handleCopyChartImage(chart: ChartResult["charts"][number]) {
    try {
      const response = await fetch(chart.url);
      const blob = await response.blob();
      if ("ClipboardItem" in window && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
        setChartCopyStatus(`${chart.metric ?? "summary"} 图片已复制`);
      } else {
        await navigator.clipboard.writeText(new URL(chart.url, window.location.origin).href);
        setChartCopyStatus("浏览器不支持复制图片，已复制路径");
      }
      window.setTimeout(() => setChartCopyStatus(""), 1800);
    } catch {
      setChartCopyStatus("复制图片失败");
    }
  }

  return (
    <main className="app-shell">
      <section className="top-band">
        <div>
          <p className="eyebrow">Local A/B Test Workbench</p>
          <h1>产品增长实验分析工作台</h1>
          <p className="hero-copy">
            把 Excel 实验数据转成可解释的显著性结论、质量关口和可分享图表，适合本地复盘、面试演示和业务数据保护场景。
          </p>
          <div className="hero-tags" aria-label="能力标签">
            <span>Excel 导入</span>
            <span>字段识别</span>
            <span>显著性检验</span>
            <span>图表输出</span>
          </div>
        </div>
        <div className={apiOnline ? "api-pill online" : "api-pill"}>
          <Activity size={18} />
          {apiOnline ? "API 已连接" : "API 待连接"}
        </div>
      </section>

      <section className="status-grid" aria-label="状态概览">
        {statusItems.map((item) => (
          <div className={`status-cell ${item.tone}`} key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </section>

      <section className="workspace-grid">
        <aside className="config-panel">
          <div className="panel-heading">
            <FileSpreadsheet size={20} />
            <div>
              <p className="step-label">Step 1</p>
              <h2>文件与字段</h2>
            </div>
          </div>
          <div className="quick-start-card">
            <div>
              <p className="step-label">Quick start</p>
              <strong>没有 Excel 也能演示完整流程</strong>
              <span>一键生成 demo，自动识别字段并预选类别指标。</span>
            </div>
            <button className="secondary-button compact" type="button" onClick={() => void handleGenerateChiSquareDemo()} disabled={isGeneratingDemo}>
              <FlaskConical size={16} />
              {isGeneratingDemo ? "生成中" : "生成 demo"}
            </button>
          </div>
          <input
            ref={fileInputRef}
            className="hidden-input"
            type="file"
            accept=".xlsx,.xlsm"
            onChange={handleFileChange}
          />
          <button className="upload-zone" type="button" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
            <Upload size={22} />
            <span>{isUploading ? "上传并识别中" : "上传 Excel"}</span>
            <small>.xlsx / .xlsm</small>
          </button>

          {error && <div className="error-banner">{error}</div>}

          {upload && (
            <div className="file-summary">
              <strong>{upload.filename}</strong>
              <span>{formatBytes(upload.file_size)}</span>
            </div>
          )}

          {upload && (
            <div className="field-block">
              <label>Sheet</label>
              <select value={selectedSheet} onChange={(event) => void handleSheetChange(event.target.value)}>
                {upload.sheets.map((sheet) => (
                  <option key={sheet} value={sheet}>
                    {sheet}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="field-block">
            <label>分组字段</label>
            <select
              value={groupField}
              disabled={!headers}
              onChange={(event) => {
                setGroupField(event.target.value);
                setAnovaFactorFields((current) => current.filter((field) => field !== event.target.value));
              }}
            >
              <option value="">选择自变量</option>
              {headers?.columns.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field-block">
            <label>ANOVA 自变量（可选）</label>
            <div className="factor-hint">默认包含分组字段；这里最多再选 2 个分类因子，用于主效应和交互作用检验。</div>
            <div className="metric-list compact">
              {headers ? (
                headers.columns.map((column) => (
                  <label className="metric-option" key={column.name}>
                    <input
                      type="checkbox"
                      checked={anovaFactorFields.includes(column.name)}
                      disabled={
                        column.name === groupField ||
                        metricFields.includes(column.name) ||
                        (!anovaFactorFields.includes(column.name) && anovaFactorFields.length >= 2)
                      }
                      onChange={() => toggleAnovaFactor(column.name)}
                    />
                    <span>{column.name}</span>
                    <em>{column.dtype}</em>
                  </label>
                ))
              ) : (
                <div className="metric-empty">选择分组字段后，可补充交互因子</div>
              )}
            </div>
          </div>

          <div className="field-block">
            <label>分析指标</label>
            <div className="metric-list">
              {headers ? (
                headers.columns.map((column) => (
                  <label className="metric-option" key={column.name}>
                    <input
                      type="checkbox"
                      checked={metricFields.includes(column.name)}
                      disabled={
                        column.name === groupField ||
                        anovaFactorFields.includes(column.name) ||
                        (!metricFields.includes(column.name) && metricFields.length >= 5)
                      }
                      onChange={() => toggleMetric(column.name)}
                    />
                    <span>{column.name}</span>
                    <em>{column.dtype}</em>
                  </label>
                ))
              ) : (
                <div className="metric-empty">最多选择 5 个因变量</div>
              )}
            </div>
          </div>

          <details className="debug-panel">
            <summary>
              <FlaskConical size={16} />
              更多调试工具
            </summary>
            <button className="secondary-button" type="button" onClick={() => void handleGenerateChiSquareDemo()} disabled={isGeneratingDemo}>
              {isGeneratingDemo ? "生成中" : "生成卡方检验样例"}
            </button>
          </details>
        </aside>

        <section className="main-panel">
          <div className="workflow-strip" aria-label="工作流">
            {workflowCards.map(([title, detail]) => (
              <div className="workflow-card" key={title}>
                <span>{title}</span>
                <strong>{detail}</strong>
              </div>
            ))}
          </div>
          <div className="action-row">
            <button className="primary-button" type="button" disabled={!canAnalyze || isAnalyzing} onClick={() => void handleAnalyze()}>
              {isAnalyzing ? "Step 2 分析中" : "Step 2 分析 Excel"}
            </button>
            <button className="primary-button muted" type="button" disabled={!canPlot || isPlotting} onClick={() => void handleGenerateCharts()}>
              {isPlotting ? "Step 3 生成中" : "Step 3 生成图表"}
            </button>
            <button className="icon-button" type="button" aria-label="问题上报待补齐" title="问题上报待补齐" disabled>
              <Bug size={20} />
            </button>
          </div>

          <div className="summary-band">
            <div>
              <p className="eyebrow">分析摘要</p>
              <h2>{summaryTitle(headers, analysis)}</h2>
              {analysis ? (
                <ExpandableText className="summary-conclusion" text={analysis.pm_conclusion} />
              ) : (
                <p className="summary-empty">
                  先上传 Excel 或生成 demo。完成字段识别后，选择分组字段和 1-5 个指标即可执行分析。
                </p>
              )}
            </div>
            <span className={analysis?.gate_status === "PASS" ? "warning-chip pass" : "warning-chip"}>
              <AlertTriangle size={16} />
              {analysis ? `${analysis.gate_status} · ${analysis.warnings.length} WARNING` : "暂无 WARNING"}
            </span>
          </div>

          <div className="content-grid">
            <div className="result-table">
              <div className="section-title-row">
                <div>
                  <p className="step-label">Step 2</p>
                  <strong>分析结果</strong>
                </div>
              </div>
              {analysis ? (
                <>
                  <div className="analysis-meta">
                    <div className="analysis-chips">
                      <span>Gate: {analysis.gate_status}</span>
                      <span>指标数: {analysis.tables.primary_metric_test.length}</span>
                      <span>显著: {analysis.tables.primary_metric_test.filter((row) => row.significant === "YES").length}</span>
                    </div>
                    <button className="copy-button" type="button" onClick={() => void handleCopyAnalysisTable()}>
                      <Copy size={16} />
                      {copyStatus || "复制表格"}
                    </button>
                  </div>
                  <div className="metric-result-table">
                    <div className="metric-result-header">
                      <span>指标</span>
                      <span>A 组</span>
                      <span>B 组</span>
                      <span>差异</span>
                      <span>p 值</span>
                      <span>显著</span>
                    </div>
                    {analysis.tables.primary_metric_test.map((row) => (
                      <div className="metric-result-row" key={String(row.metric)}>
                        <span title={String(row.metric)}>{row.metric}</span>
                        <span>{row.group_a_value}</span>
                        <span>{row.group_b_value}</span>
                        <span>{row.absolute_diff}</span>
                        <span>{row.p_value}</span>
                        <strong className={row.significant === "YES" ? "sig-yes" : "sig-no"}>{row.significant}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="method-note-panel">
                    <strong>统计方法说明</strong>
                    {methodNotes(analysis).map((note) => (
                      <ExpandableText className="method-note" key={note.method} prefix={note.method} text={note.detail} />
                    ))}
                  </div>
                  {hasAnovaRows(analysis) && (
                    <div className="anova-panel">
                      <div className="section-title-row flat">
                        <div>
                          <p className="step-label">ANOVA</p>
                          <strong>多自变量方差分析</strong>
                        </div>
                        <span>{analysis.requested_anova_factor_fields?.length ? `额外因子 ${analysis.requested_anova_factor_fields.length} 个` : "未选择额外因子"}</span>
                      </div>
                      <div className="anova-result-table">
                        <div className="anova-result-header">
                          <span>指标</span>
                          <span>项</span>
                          <span>类型</span>
                          <span>F</span>
                          <span>p 值</span>
                          <span>显著</span>
                        </div>
                        {analysis.tables.anova_tests?.map((row, index) => (
                          <div className="anova-result-row" key={`${row.metric ?? "anova"}-${row.term ?? index}`}>
                            <span title={String(row.metric ?? "")}>{row.metric}</span>
                            <span title={String(row.term ?? row.message ?? "")}>{row.term || row.message}</span>
                            <span>{row.term_type}</span>
                            <span>{row.f_value}</span>
                            <span>{row.p_value}</span>
                            <strong className={row.significant === "YES" ? "sig-yes" : "sig-no"}>{row.significant}</strong>
                          </div>
                        ))}
                      </div>
                      <div className="method-note-panel">
                        <ExpandableText
                          prefix="ANOVA 说明"
                          text="ANOVA 使用分组字段加额外自变量作为因子，只对连续数值型因变量计算；结果会分别展示主效应和两两交互项，p<0.05 标记为显著。"
                        />
                      </div>
                    </div>
                  )}
                  <div className="conclusion-box">
                    <ExpandableText prefix="PM 结论" text={analysis.pm_conclusion} />
                  </div>
                </>
              ) : headers ? (
                headers.columns.map((column) => (
                  <div className="result-row" key={column.name}>
                    <span>{column.name}</span>
                    <strong>{column.dtype}</strong>
                    <small>{column.sample_values.length ? column.sample_values.join(", ") : "暂无样例"}</small>
                  </div>
                ))
              ) : (
                resultRows.map((row) => (
                  <div className="result-row" key={row[0]}>
                    <span>{row[0]}</span>
                    <strong>{row[1]}</strong>
                    <small>{row[2]}</small>
                  </div>
                ))
              )}
            </div>

            <div className="chart-preview">
              <div className="section-title-row">
                <div>
                  <p className="step-label">Step 3</p>
                  <strong>图表输出</strong>
                </div>
                {chartCopyStatus && <span className="inline-status">{chartCopyStatus}</span>}
              </div>
              {charts ? (
                <div className="chart-grid">
                  {charts.charts.map((chart) => (
                    <div className="chart-card" key={chart.chart_id}>
                      <button className="chart-thumb" type="button" onClick={() => setSelectedChart(chart)}>
                        <img src={chart.url} alt={chart.metric ?? "summary"} />
                      </button>
                      <span title={chart.metric ?? "summary"}>{chart.metric ?? "summary"}</span>
                      <div className="chart-actions">
                        <button
                          type="button"
                          aria-label="复制图片"
                          title="复制图片"
                          onClick={() => void handleCopyChartImage(chart)}
                        >
                          <Image size={16} />
                        </button>
                        <button
                          type="button"
                          aria-label="复制路径"
                          title="复制路径"
                          onClick={() => void handleCopyChartPath(chart)}
                        >
                          <Link size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {charts.skipped_metrics?.map((skipped) => (
                    <div className="chart-skip-card" key={skipped.metric}>
                      <strong>{skipped.metric}</strong>
                      <ExpandableText prefix="未生成图表" text={skipped.reason} />
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <div className="chart-placeholder">
                    <BarChart3 size={34} />
                    <span>{analysis ? "分析已完成，可以生成图表" : groupField ? `分组字段：${groupField}` : "先选择分组字段"}</span>
                  </div>
                  <div className="chart-placeholder soft">
                    <LineChart size={34} />
                    <span>{analysis ? analysis.output_path.split("/").pop() : metricFields.length ? `${metricFields.length} 个指标已选择` : "再选择分析指标"}</span>
                  </div>
                </>
              )}
              {analysis?.warnings.map((warning) => (
                <div className="warning-note" key={warning.check}>
                  <strong>{warning.check}</strong>
                  <ExpandableText text={warning.detail} />
                </div>
              ))}
            </div>
          </div>
        </section>
      </section>

      {selectedChart && (
        <div className="image-lightbox" role="dialog" aria-modal="true" aria-label="图表预览" onClick={() => setSelectedChart(null)}>
          <div className="lightbox-content" onClick={(event) => event.stopPropagation()}>
            <div className="lightbox-header">
              <strong>{selectedChart.metric ?? "summary"}</strong>
              <span>{chartPositionLabel(charts, selectedChart)}</span>
              <button className="lightbox-close" type="button" aria-label="关闭预览" onClick={() => setSelectedChart(null)}>
                <X size={20} />
              </button>
            </div>
            {charts && charts.charts.length > 1 && (
              <>
                <button className="lightbox-nav prev" type="button" aria-label="上一张图" onClick={() => moveSelectedChart(-1)}>
                  <ChevronLeft size={26} />
                </button>
                <button className="lightbox-nav next" type="button" aria-label="下一张图" onClick={() => moveSelectedChart(1)}>
                  <ChevronRight size={26} />
                </button>
              </>
            )}
            <img src={selectedChart.url} alt={selectedChart.metric ?? "summary"} />
          </div>
        </div>
      )}
    </main>
  );
}

function ExpandableText({
  text,
  prefix,
  className
}: {
  text: string;
  prefix?: string;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLong = text.length > 120;
  return (
    <div className={className ? `expandable-text ${className}` : "expandable-text"}>
      <p className={expanded ? "expanded" : ""}>
        {prefix && <span>{prefix}</span>}
        {text}
      </p>
      {isLong && (
        <button type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起" : "展开"}
        </button>
      )}
    </div>
  );
}

function summaryTitle(headers: HeaderDetection | null, analysis: AnalysisResult | null) {
  if (analysis) {
    const rows = analysis.tables.primary_metric_test;
    const significantCount = rows.filter((row) => row.significant === "YES").length;
    const unsupportedCount = rows.filter((row) => row.chartable === "NO" || row.significant === "无法计算").length;
    const calculableCount = rows.length - unsupportedCount;
    if (unsupportedCount > 0) {
      return `已分析 ${rows.length} 个指标：${calculableCount} 个可计算，${unsupportedCount} 个无法计算，${significantCount} 个显著`;
    }
    return `已分析 ${rows.length} 个指标：${significantCount} 个达到统计显著，Gate=${analysis.gate_status}`;
  }
  if (headers) return `已识别 ${headers.columns.length} 个字段，${headers.row_count} 行数据`;
  return "上传文件后，这里会展示主结论";
}

function chartPositionLabel(charts: ChartResult | null, selectedChart: ChartResult["charts"][number]) {
  if (!charts) return "";
  const index = charts.charts.findIndex((chart) => chart.chart_id === selectedChart.chart_id);
  if (index < 0) return "";
  return `${index + 1} / ${charts.charts.length}`;
}

function defaultGroupField(headers: HeaderDetection) {
  const preferred = headers.columns.find((column) => column.name.toLowerCase() === "group_id");
  return preferred?.name ?? "";
}

function defaultChiSquareMetrics(headers: HeaderDetection) {
  const preferred = ["outcome_category", "reward_preference"];
  const available = new Set(headers.columns.map((column) => column.name));
  return preferred.filter((field) => available.has(field));
}

function orderMetricsBySheet(headers: HeaderDetection | null, metricFields: string[]) {
  if (!headers) return metricFields;
  const selected = new Set(metricFields);
  return headers.columns.map((column) => column.name).filter((name) => selected.has(name));
}

function methodNotes(analysis: AnalysisResult) {
  const seen = new Set<string>();
  return analysis.tables.primary_metric_test
    .map((row) => ({
      method: String(row.statistical_method || "未标注方法"),
      detail: String(row.method_note || "该指标使用系统自动识别的统计检验方法。")
    }))
    .filter((note) => {
      const key = `${note.method}|${note.detail}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function hasAnovaRows(analysis: AnalysisResult) {
  const rows = analysis.tables.anova_tests ?? [];
  return rows.length > 0 && !("message" in rows[0] && rows.length === 1 && !analysis.requested_anova_factor_fields?.length);
}

function buildAnalysisTableText(analysis: AnalysisResult) {
  const columns = [
    ["metric", "指标"],
    ["metric_type", "类型"],
    ["group_a_value", "A 组"],
    ["group_b_value", "B 组"],
    ["absolute_diff", "差异"],
    ["relative_lift", "相对提升"],
    ["p_value", "p 值"],
    ["ci_95", "95% CI"],
    ["chi_square", "卡方值"],
    ["df", "自由度"],
    ["significant", "显著"],
    ["statistical_method", "统计方法"]
  ];
  const header = columns.map(([, label]) => label).join("\t");
  const rows = analysis.tables.primary_metric_test.map((row) =>
    columns.map(([key]) => String(row[key] ?? "").replace(/\s+/g, " ")).join("\t")
  );
  const anovaRows = analysis.tables.anova_tests ?? [];
  if (!anovaRows.length) return [header, ...rows].join("\n");
  const anovaColumns = [
    ["metric", "ANOVA 指标"],
    ["term", "项"],
    ["term_type", "类型"],
    ["df_term", "项自由度"],
    ["df_error", "误差自由度"],
    ["f_value", "F 值"],
    ["p_value", "p 值"],
    ["significant", "显著"],
    ["note", "说明"]
  ];
  const anovaHeader = anovaColumns.map(([, label]) => label).join("\t");
  const anovaBody = anovaRows.map((row) => anovaColumns.map(([key]) => String(row[key] ?? "").replace(/\s+/g, " ")).join("\t"));
  return [header, ...rows, "", anovaHeader, ...anovaBody].join("\n");
}

async function detectHeaders(uploadId: string, sheetName: string) {
  const response = await fetch(`${apiBase}/uploads/${uploadId}/detect-headers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sheet_name: sheetName, header_row: null, preview_rows: 20 })
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as HeaderDetection;
}

async function readError(response: Response) {
  try {
    const payload = await response.json();
    return payload.detail ?? "请求失败";
  } catch {
    return "请求失败";
  }
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

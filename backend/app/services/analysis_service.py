import json
import math
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.core.paths import STORAGE_ROOT, ensure_storage_dirs
from app.schemas.analysis import AnalysisRequest


ALPHA = 0.05


def run_analysis(request: AnalysisRequest) -> dict[str, object]:
    ensure_storage_dirs()
    upload_dir = STORAGE_ROOT / "uploads" / request.upload_id
    input_path = upload_dir / "original.xlsx"
    if not input_path.exists():
        raise FileNotFoundError(f"Upload not found: {request.upload_id}")

    df = pd.read_excel(input_path, sheet_name=request.sheet_name)
    validate_request_columns(df, request)

    job_id = f"job_{uuid4().hex[:12]}"
    job_dir = STORAGE_ROOT / "jobs" / job_id
    result_dir = STORAGE_ROOT / "results" / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    result_dir.mkdir(parents=True, exist_ok=False)

    output_path = result_dir / "stage2_result.xlsx"
    _write_json(job_dir / "request.json", request.model_dump())
    _write_json(job_dir / "status.json", {"job_id": job_id, "status": "running"})

    validation_df, gate_status, group_values = build_quality_gate(df, request)
    sample_df = build_sample_size(df, request, group_values)
    metric_tests_df = build_metric_tests(df, request, group_values)
    anova_df = build_anova_tests(df, request)
    observation_df = build_observation_table(metric_tests_df)
    segment_df = build_segment_diagnostics(df, request, group_values)
    conclusion_df = build_pm_conclusion(gate_status, metric_tests_df, validation_df, request, anova_df)

    write_output(
        output_path=output_path,
        validation_df=validation_df,
        sample_df=sample_df,
        metric_tests_df=metric_tests_df,
        anova_df=anova_df,
        observation_df=observation_df,
        segment_df=segment_df,
        conclusion_df=conclusion_df,
    )

    summary = read_stage2_summary(output_path)
    summary.update(
        {
            "job_id": job_id,
            "status": "completed",
            "output_path": str(output_path),
            "workbook_url": f"/api/analysis/jobs/{job_id}/workbook",
            "requested_group_field": request.group_field,
            "requested_metric_fields": request.metric_fields,
            "requested_anova_factor_fields": request.anova_factor_fields,
        }
    )
    _write_json(result_dir / "stage2_result.json", summary)
    _write_json(job_dir / "status.json", {"job_id": job_id, "status": "completed"})
    return summary


def validate_request_columns(df: pd.DataFrame, request: AnalysisRequest) -> None:
    missing = [field for field in [request.group_field, *request.metric_fields, *request.anova_factor_fields] if field not in df.columns]
    if missing:
        raise ValueError(f"Selected fields are missing from sheet: {missing}")
    if request.group_field in request.metric_fields:
        raise ValueError("Group field cannot also be a metric field.")
    overlap = sorted(set(request.metric_fields) & set(request.anova_factor_fields))
    if overlap:
        raise ValueError(f"ANOVA factor fields cannot also be metric fields: {overlap}")


def build_quality_gate(df: pd.DataFrame, request: AnalysisRequest) -> tuple[pd.DataFrame, str, list[str]]:
    checks: list[dict[str, object]] = []

    group_series = df[request.group_field].dropna()
    group_values = sorted([str(value) for value in group_series.unique().tolist()])
    add_check(checks, "group_field_present", "PASS", request.group_field)
    add_check(
        checks,
        "two_groups_only",
        "PASS" if len(group_values) == 2 else "FAIL",
        f"groups={group_values}",
    )

    if len(group_values) != 2:
        gate = "FAIL"
        checks.append({"check": "overall_gate_status", "status": gate, "detail": "requires exactly two groups"})
        return pd.DataFrame(checks), gate, group_values

    counts = df[df[request.group_field].astype(str).isin(group_values)].groupby(request.group_field).size().to_dict()
    count_values = [int(counts.get(group, 0)) for group in group_values]
    add_check(checks, "group_sample_size_present", "PASS" if min(count_values) > 0 else "FAIL", f"counts={counts}")
    imbalance = abs(count_values[1] - count_values[0]) / max(max(count_values), 1)
    add_check(
        checks,
        "group_sample_size_roughly_balanced",
        "PASS" if imbalance <= 0.1 else "WARNING",
        f"counts={counts}, imbalance={imbalance:.2%}",
    )

    for metric in request.metric_fields:
        metric_series = df[metric]
        metric_type = infer_metric_type(metric_series)
        valid_count = int(metric_series.dropna().astype(str).str.strip().ne("").sum())
        add_check(
            checks,
            f"{metric}_supported_metric_type",
            "PASS" if metric_type != "unsupported" else "WARNING",
            f"有效行数={valid_count}；识别类型={metric_type}",
        )
        add_check(checks, f"{metric}_detected_type", "PASS", metric_type)

    anova_factors = anova_factor_fields(request)
    if request.anova_factor_fields:
        add_check(
            checks,
            "anova_factor_count",
            "PASS" if len(anova_factors) >= 2 else "WARNING",
            f"factors={anova_factors}",
        )
        for factor in anova_factors:
            factor_values = df[factor].dropna().astype(str).str.strip()
            unique_count = factor_values[factor_values != ""].nunique()
            add_check(
                checks,
                f"{factor}_anova_factor_levels",
                "PASS" if 2 <= unique_count <= 20 else "WARNING",
                f"levels={unique_count}",
            )

    statuses = {str(row["status"]) for row in checks}
    gate = "FAIL" if "FAIL" in statuses else ("PASS_WITH_WARNING" if "WARNING" in statuses else "PASS")
    detail = "hard checks passed; warnings present" if gate == "PASS_WITH_WARNING" else ("all checks passed" if gate == "PASS" else "hard check failed")
    checks.append({"check": "overall_gate_status", "status": gate, "detail": detail})
    return pd.DataFrame(checks), gate, group_values


def build_sample_size(df: pd.DataFrame, request: AnalysisRequest, group_values: list[str]) -> pd.DataFrame:
    rows = []
    for metric in request.metric_fields:
        for group in group_values:
            part = df[df[request.group_field].astype(str) == group]
            valid = valid_metric_values(part[metric])
            rows.append(
                {
                    "metric": metric,
                    "group_field": request.group_field,
                    "group": group,
                    "row_count": len(part),
                    "valid_metric_count": int(valid.count()),
                    "missing_metric_count": int(len(part) - valid.count()),
                }
            )
    return pd.DataFrame(rows)


def build_metric_tests(df: pd.DataFrame, request: AnalysisRequest, group_values: list[str]) -> pd.DataFrame:
    group_a, group_b = group_values
    rows = []
    for metric in request.metric_fields:
        raw_a = df.loc[df[request.group_field].astype(str) == group_a, metric]
        raw_b = df.loc[df[request.group_field].astype(str) == group_b, metric]
        metric_type = infer_metric_type(pd.concat([raw_a, raw_b], ignore_index=True))
        method_name, method_note = metric_method(metric_type)
        if metric_type == "unsupported":
            rows.append(
                {
                    "metric": metric,
                    "metric_type": metric_type,
                    "group_a_label": group_a,
                    "group_b_label": group_b,
                    "group_a_value": "",
                    "group_b_value": "",
                    "group_a_n": int(valid_metric_values(raw_a).count()),
                    "group_b_n": int(valid_metric_values(raw_b).count()),
                    "absolute_diff": "",
                    "relative_lift": "",
                    "p_value": "",
                    "ci_95": "",
                    "chi_square": "",
                    "df": "",
                    "contingency_table": "",
                    "significant": "无法计算",
                    "chartable": "NO",
                    "statistical_method": method_name,
                    "method_note": method_note,
                    "note": "无法进行显著性分析：当前因变量不是可识别的 0/1 二元指标或连续数值指标。",
                }
            )
            continue

        if metric_type == "binary":
            a = pd.to_numeric(raw_a, errors="coerce").dropna()
            b = pd.to_numeric(raw_b, errors="coerce").dropna()
            test = two_sample_prop_test(int(a.sum()), int(a.count()), int(b.sum()), int(b.count()))
            a_value = pct_value(test["group_a_value_num"])
            b_value = pct_value(test["group_b_value_num"])
            diff = pp_value(test["absolute_diff_num"])
            ci = f"[{pp_value(test['ci_low_num'])}, {pp_value(test['ci_high_num'])}]"
            group_a_n = int(a.count())
            group_b_n = int(b.count())
            chi_square = ""
            df_value = ""
            contingency_json = ""
        elif metric_type == "categorical":
            test = chi_square_test(df, request.group_field, metric, group_values)
            a_value = test["group_a_value"]
            b_value = test["group_b_value"]
            diff = ""
            ci = ""
            group_a_n = int(test["group_a_n"])
            group_b_n = int(test["group_b_n"])
            chi_square = round(test["chi_square"], 6) if not math.isnan(test["chi_square"]) else ""
            df_value = int(test["df"])
            contingency_json = json.dumps(test["contingency_table"], ensure_ascii=False)
        else:
            a = pd.to_numeric(raw_a, errors="coerce").dropna()
            b = pd.to_numeric(raw_b, errors="coerce").dropna()
            test = mean_test(a, b)
            a_value = numeric_value(test["group_a_value_num"])
            b_value = numeric_value(test["group_b_value_num"])
            diff = signed_numeric_value(test["absolute_diff_num"])
            ci = f"[{signed_numeric_value(test['ci_low_num'])}, {signed_numeric_value(test['ci_high_num'])}]"
            group_a_n = int(a.count())
            group_b_n = int(b.count())
            chi_square = ""
            df_value = ""
            contingency_json = ""

        p_value = test["p_value"]
        significant = bool(not math.isnan(p_value) and p_value < ALPHA)
        rows.append(
            {
                "metric": metric,
                "metric_type": metric_type,
                "group_a_label": group_a,
                "group_b_label": group_b,
                "group_a_value": a_value,
                "group_b_value": b_value,
                "group_a_n": group_a_n,
                "group_b_n": group_b_n,
                "absolute_diff": diff,
                "relative_lift": pct_value(test["relative_lift_num"]),
                "p_value": round(p_value, 6) if not math.isnan(p_value) else "",
                "ci_95": ci,
                "chi_square": chi_square,
                "df": df_value,
                "contingency_table": contingency_json,
                "significant": "YES" if significant else "NO",
                "chartable": "YES",
                "statistical_method": method_name,
                "method_note": method_note,
                "note": build_metric_note(metric_type, significant, test["absolute_diff_num"]),
            }
        )
    return pd.DataFrame(rows)


def build_observation_table(metric_tests_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in metric_tests_df.to_dict(orient="records"):
        copied = dict(row)
        copied["note"] = f"{copied.get('note', '')}; selected metric test, interpret with configured business context"
        rows.append(copied)
    return pd.DataFrame(rows)


def build_segment_diagnostics(df: pd.DataFrame, request: AnalysisRequest, group_values: list[str]) -> pd.DataFrame:
    if "is_new_user" not in df.columns:
        return pd.DataFrame([{"message": "segment diagnostics skipped: is_new_user column not found"}])

    rows = []
    group_a, group_b = group_values
    for metric in request.metric_fields:
        for segment_value, segment_name in [(1, "new_users"), (0, "old_users")]:
            part = df[df["is_new_user"] == segment_value]
            a = pd.to_numeric(part.loc[part[request.group_field].astype(str) == group_a, metric], errors="coerce").dropna()
            b = pd.to_numeric(part.loc[part[request.group_field].astype(str) == group_b, metric], errors="coerce").dropna()
            if a.empty or b.empty:
                continue
            metric_type = infer_metric_type(pd.concat([part.loc[part[request.group_field].astype(str) == group_a, metric], part.loc[part[request.group_field].astype(str) == group_b, metric]], ignore_index=True))
            if metric_type in {"unsupported", "categorical"}:
                continue
            a_value_num = float(a.mean())
            b_value_num = float(b.mean())
            diff = b_value_num - a_value_num
            rows.append(
                {
                    "metric": metric,
                    "segment": segment_name,
                    "group_a_label": group_a,
                    "group_b_label": group_b,
                    "group_a_n": int(a.count()),
                    "group_b_n": int(b.count()),
                    "group_a_value": pct_value(a_value_num) if metric_type == "binary" else numeric_value(a_value_num),
                    "group_b_value": pct_value(b_value_num) if metric_type == "binary" else numeric_value(b_value_num),
                    "absolute_diff": pp_value(diff) if metric_type == "binary" else signed_numeric_value(diff),
                    "diagnosis": "direction_consistent_B_gt_A" if diff > 0 else ("direction_flat" if abs(diff) < 1e-12 else "direction_inconsistent_B_lt_A"),
                }
            )
    return pd.DataFrame(rows or [{"message": "segment diagnostics found no comparable segments"}])


def build_anova_tests(df: pd.DataFrame, request: AnalysisRequest) -> pd.DataFrame:
    factors = anova_factor_fields(request)
    if len(factors) < 2:
        return pd.DataFrame([{"message": "ANOVA skipped: select at least one additional independent variable besides the group field"}])

    rows: list[dict[str, object]] = []
    for metric in request.metric_fields:
        metric_type = infer_metric_type(df[metric])
        if metric_type != "numeric":
            rows.append(
                {
                    "metric": metric,
                    "factors": " + ".join(factors),
                    "term": "",
                    "term_type": "",
                    "df_term": "",
                    "df_error": "",
                    "f_value": "",
                    "p_value": "",
                    "significant": "无法计算",
                    "note": "ANOVA 仅用于连续数值型因变量；二元、类别或无法识别的指标请查看对应的比例检验、卡方检验或 unsupported 标记。",
                }
            )
            continue
        rows.extend(factorial_anova(df, metric, factors))

    return pd.DataFrame(rows or [{"message": "ANOVA skipped: no comparable numeric metrics"}])


def anova_factor_fields(request: AnalysisRequest) -> list[str]:
    fields: list[str] = []
    for field in [request.group_field, *request.anova_factor_fields]:
        if field and field not in fields:
            fields.append(field)
    return fields


def factorial_anova(df: pd.DataFrame, metric: str, factors: list[str]) -> list[dict[str, object]]:
    working = df[[metric, *factors]].copy()
    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    working = working.dropna(subset=[metric, *factors])
    for factor in factors:
        working[factor] = working[factor].astype(str).str.strip()
        working = working[working[factor] != ""]
    if len(working) < 8:
        return [anova_unavailable_row(metric, factors, "ANOVA 可用样本过少，无法稳定估计主效应和交互项。")]

    design = pd.DataFrame({"Intercept": [1.0] * len(working)}, index=working.index)
    term_columns: dict[str, list[str]] = {"Intercept": ["Intercept"]}
    main_dummy_columns: dict[str, list[str]] = {}

    for factor in factors:
        dummies = pd.get_dummies(working[factor], prefix=factor, drop_first=True, dtype=float)
        if dummies.empty:
            continue
        design = pd.concat([design, dummies], axis=1)
        main_dummy_columns[factor] = dummies.columns.tolist()
        term_columns[factor] = dummies.columns.tolist()

    pair_terms: list[str] = []
    for left_index, left in enumerate(factors):
        for right in factors[left_index + 1 :]:
            interaction_cols: list[str] = []
            for left_col in main_dummy_columns.get(left, []):
                for right_col in main_dummy_columns.get(right, []):
                    name = f"{left_col}:{right_col}"
                    design[name] = design[left_col] * design[right_col]
                    interaction_cols.append(name)
            if interaction_cols:
                term = f"{left}:{right}"
                term_columns[term] = interaction_cols
                pair_terms.append(term)

    y = working[metric].to_numpy(dtype=float)
    full_columns = design.columns.tolist()
    full_rss, full_rank = ols_rss(design[full_columns], y)
    df_error = len(y) - full_rank
    if df_error <= 0 or math.isnan(full_rss):
        return [anova_unavailable_row(metric, factors, "ANOVA 模型自由度不足，请减少自变量层级或增加样本量。")]

    rows: list[dict[str, object]] = []
    for term in [*factors, *pair_terms]:
        removed = term_columns.get(term, [])
        if not removed:
            continue
        reduced_columns = [column for column in full_columns if column not in removed]
        reduced_rss, reduced_rank = ols_rss(design[reduced_columns], y)
        df_term = max(full_rank - reduced_rank, 0)
        if df_term <= 0 or math.isnan(reduced_rss):
            f_value = math.nan
            p_value = math.nan
        else:
            numerator = max((reduced_rss - full_rss) / df_term, 0.0)
            denominator = full_rss / df_error if df_error else math.nan
            f_value = numerator / denominator if denominator and not math.isnan(denominator) else math.nan
            p_value = f_sf(f_value, df_term, df_error) if not math.isnan(f_value) else math.nan
        rows.append(
            {
                "metric": metric,
                "factors": " + ".join(factors),
                "term": term,
                "term_type": "interaction" if ":" in term else "main_effect",
                "df_term": int(df_term) if df_term else "",
                "df_error": int(df_error),
                "f_value": round(f_value, 6) if not math.isnan(f_value) else "",
                "p_value": round(p_value, 6) if not math.isnan(p_value) else "",
                "significant": "YES" if not math.isnan(p_value) and p_value < ALPHA else "NO",
                "note": "多因素 ANOVA：检验该主效应或交互项是否解释连续因变量差异；alpha=0.05。",
            }
        )
    return rows or [anova_unavailable_row(metric, factors, "ANOVA 没有可估计的主效应或交互项。")]


def anova_unavailable_row(metric: str, factors: list[str], note: str) -> dict[str, object]:
    return {
        "metric": metric,
        "factors": " + ".join(factors),
        "term": "",
        "term_type": "",
        "df_term": "",
        "df_error": "",
        "f_value": "",
        "p_value": "",
        "significant": "无法计算",
        "note": note,
    }


def ols_rss(x: pd.DataFrame, y: object) -> tuple[float, int]:
    import numpy as np

    matrix = x.to_numpy(dtype=float)
    target = np.asarray(y, dtype=float)
    try:
        coef, _, rank, _ = np.linalg.lstsq(matrix, target, rcond=None)
    except np.linalg.LinAlgError:
        return math.nan, 0
    residual = target - matrix @ coef
    return float((residual ** 2).sum()), int(rank)


def build_pm_conclusion(gate_status: str, metric_tests_df: pd.DataFrame, validation_df: pd.DataFrame, request: AnalysisRequest, anova_df: pd.DataFrame) -> pd.DataFrame:
    warnings = validation_df[validation_df["status"] == "WARNING"]
    warning_text = "；".join(f"{translate_field_name(str(row.check))}: {row.detail}" for row in warnings.itertuples()) or "无"
    significant_count = int((metric_tests_df["significant"] == "YES").sum()) if "significant" in metric_tests_df else 0
    metric_count = len(metric_tests_df)
    group_name = translate_field_name(request.group_field)
    calculable_rows = metric_tests_df[metric_tests_df.get("chartable", "") != "NO"] if "chartable" in metric_tests_df else metric_tests_df
    unsupported_rows = metric_tests_df[metric_tests_df.get("chartable", "") == "NO"] if "chartable" in metric_tests_df else pd.DataFrame()
    primary_row = calculable_rows.iloc[0] if not calculable_rows.empty else None
    if unsupported_rows.empty:
        unsupported_text = ""
    else:
        unsupported_names = "、".join(translate_field_name(str(row.metric)) for row in unsupported_rows.itertuples())
        unsupported_text = f"；{unsupported_names} 无法计算"
    if primary_row is not None:
        evidence_text = compact_metric_conclusion(primary_row)
    else:
        evidence_text = "没有可计算指标"
    anova_text = ""
    if "significant" in anova_df and len(anova_factor_fields(request)) >= 2:
        anova_sig_count = int((anova_df["significant"] == "YES").sum())
        anova_text = f"；ANOVA 发现 {anova_sig_count} 个主效应/交互项显著"
    decision_text = (
        f"{significant_count} 个指标显著"
        if significant_count
        else "没有指标达到显著"
    )
    conclusion = (
        f"以「{group_name}」分组，分析 {metric_count} 个指标，Gate={gate_status}。"
        f"{decision_text}；{evidence_text}{unsupported_text}{anova_text}。"
        f"{' 风险提示：' + warning_text + '。' if warning_text != '无' else ''}"
    )
    return pd.DataFrame(
        [
            {"section": "gate_status", "content": gate_status},
            {"section": "metric_count", "content": metric_count},
            {"section": "significant_metric_count", "content": significant_count},
            {"section": "warnings", "content": warning_text},
            {"section": "pm_readable_conclusion", "content": conclusion},
        ]
    )


def metric_conclusion(row: object) -> str:
    metric_name = translate_field_name(str(row.metric))
    a_label = translate_group_label(str(row.group_a_label))
    b_label = translate_group_label(str(row.group_b_label))
    diff_num = parse_signed_display_value(str(row.absolute_diff))
    direction = "高于" if diff_num > 0 else ("低于" if diff_num < 0 else "基本持平于")
    significant = str(row.significant) == "YES"
    significance_text = "达到统计显著" if significant else "未达到统计显著"
    if direction == "基本持平于":
        comparison = f"{b_label}基本持平于{a_label}"
    else:
        comparison = f"{b_label}{direction}{a_label}"
    return (
        f"「{metric_name}」中，{a_label}={row.group_a_value}，{b_label}={row.group_b_value}，"
        f"{comparison}，差异为 {row.absolute_diff}，p={row.p_value}，95% CI={row.ci_95}，{significance_text}。"
    )


def compact_metric_conclusion(row: object) -> str:
    metric_name = translate_field_name(str(row.metric))
    if str(row.metric_type) == "categorical":
        significant = "显著相关" if str(row.significant) == "YES" else "未发现显著关联"
        return f"首个可计算指标「{metric_name}」使用卡方检验，p={row.p_value}，{significant}"
    a_label = translate_group_label(str(row.group_a_label))
    b_label = translate_group_label(str(row.group_b_label))
    diff_num = parse_signed_display_value(str(row.absolute_diff))
    direction = "提升" if diff_num > 0 else ("下降" if diff_num < 0 else "持平")
    significant = "显著" if str(row.significant) == "YES" else "未显著"
    return (
        f"首个可计算指标「{metric_name}」{b_label}较{a_label}{direction} "
        f"{row.absolute_diff}，p={row.p_value}，{significant}"
    )


def parse_signed_display_value(value: str) -> float:
    text = value.strip().replace("+", "").replace("pp", "").replace("%", "")
    try:
        parsed = float(text)
    except ValueError:
        return 0.0
    return 0.0 if abs(parsed) < 1e-12 else parsed


def translate_group_label(value: str) -> str:
    mapping = {
        "group_a": "A 组",
        "group_b": "B 组",
        "control": "对照组",
        "variant": "实验组",
        "test": "实验组",
    }
    return mapping.get(value.lower(), value)


def translate_field_name(value: str) -> str:
    mapping = {
        "uid": "玩家 ID",
        "group_id": "实验组别",
        "is_new_user": "是否新用户",
        "channel": "来源渠道",
        "platform": "平台",
        "login_days": "登录天数",
        "game_duration_min": "游戏时长",
        "retained_d1": "次日留存",
        "retained_d7": "7 日留存",
        "is_payer": "是否付费",
        "pay_amount": "付费金额",
        "lt_days": "生命周期天数",
        "ltv_amount": "生命周期价值",
        "feature_exposed": "功能曝光",
        "feature_clicked": "功能点击",
        "feature_penetration_rate": "功能渗透率",
        "outcome_category": "结果分类",
        "reward_preference": "奖励偏好",
        "session_type": "会话类型",
        "pay_rate": "付费率",
        "arpu": "ARPU",
        "arppu": "ARPPU",
    }
    normalized = value.lower()
    for suffix in ["_numeric_or_binary", "_detected_type"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    if normalized in mapping:
        return mapping[normalized]
    return value.replace("_", " ")


def two_sample_prop_test(x_a: int, n_a: int, x_b: int, n_b: int) -> dict[str, float]:
    p_a = x_a / n_a if n_a else math.nan
    p_b = x_b / n_b if n_b else math.nan
    diff = p_b - p_a
    rel = diff / p_a if p_a else math.nan
    p_pool = (x_a + x_b) / (n_a + n_b) if (n_a + n_b) else math.nan
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b)) if n_a and n_b else math.nan
    z = diff / se_pool if se_pool else math.nan
    p_value = 2 * (1 - normal_cdf(abs(z))) if not math.isnan(z) else math.nan
    se_unpooled = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b) if n_a and n_b else math.nan
    ci_low = diff - 1.96 * se_unpooled if not math.isnan(se_unpooled) else math.nan
    ci_high = diff + 1.96 * se_unpooled if not math.isnan(se_unpooled) else math.nan
    return {
        "group_a_value_num": p_a,
        "group_b_value_num": p_b,
        "absolute_diff_num": diff,
        "relative_lift_num": rel,
        "p_value": p_value,
        "ci_low_num": ci_low,
        "ci_high_num": ci_high,
    }


def mean_test(a: pd.Series, b: pd.Series) -> dict[str, float]:
    mean_a = float(a.mean()) if len(a) else math.nan
    mean_b = float(b.mean()) if len(b) else math.nan
    diff = mean_b - mean_a
    rel = diff / mean_a if mean_a else math.nan
    se = math.sqrt(float(a.var(ddof=1)) / len(a) + float(b.var(ddof=1)) / len(b)) if len(a) > 1 and len(b) > 1 else math.nan
    z = diff / se if se else math.nan
    p_value = 2 * (1 - normal_cdf(abs(z))) if not math.isnan(z) else math.nan
    ci_low = diff - 1.96 * se if not math.isnan(se) else math.nan
    ci_high = diff + 1.96 * se if not math.isnan(se) else math.nan
    return {
        "group_a_value_num": mean_a,
        "group_b_value_num": mean_b,
        "absolute_diff_num": diff,
        "relative_lift_num": rel,
        "p_value": p_value,
        "ci_low_num": ci_low,
        "ci_high_num": ci_high,
    }


def chi_square_test(df: pd.DataFrame, group_field: str, metric: str, group_values: list[str]) -> dict[str, object]:
    part = df[df[group_field].astype(str).isin(group_values)][[group_field, metric]].copy()
    part[metric] = part[metric].astype(str).str.strip()
    part = part[part[metric] != ""]
    table = pd.crosstab(part[group_field].astype(str), part[metric], dropna=False)
    table = table.reindex(index=group_values, fill_value=0)
    observed = table.to_numpy(dtype=float)
    row_totals = observed.sum(axis=1)
    col_totals = observed.sum(axis=0)
    total = observed.sum()
    if total == 0 or observed.shape[0] < 2 or observed.shape[1] < 2:
        chi_square = math.nan
        df_value = 0
        p_value = math.nan
    else:
        expected = row_totals[:, None] * col_totals[None, :] / total
        chi_square = float(((observed - expected) ** 2 / expected).sum())
        df_value = int((observed.shape[0] - 1) * (observed.shape[1] - 1))
        p_value = chi_square_sf(chi_square, df_value)

    group_a, group_b = group_values
    return {
        "group_a_value": category_distribution_text(table, group_a),
        "group_b_value": category_distribution_text(table, group_b),
        "group_a_n": int(row_totals[0]) if len(row_totals) > 0 else 0,
        "group_b_n": int(row_totals[1]) if len(row_totals) > 1 else 0,
        "absolute_diff_num": math.nan,
        "relative_lift_num": math.nan,
        "p_value": p_value,
        "ci_low_num": math.nan,
        "ci_high_num": math.nan,
        "chi_square": chi_square,
        "df": df_value,
        "contingency_table": {
            str(index): {str(column): int(value) for column, value in row.items()}
            for index, row in table.astype(int).iterrows()
        },
    }


def category_distribution_text(table: pd.DataFrame, group: str) -> str:
    if group not in table.index:
        return ""
    row = table.loc[group]
    total = int(row.sum())
    if total == 0:
        return ""
    top_category = str(row.idxmax())
    top_rate = float(row.max() / total)
    return f"{top_category} {top_rate * 100:.1f}%"


def infer_metric_type(series: pd.Series) -> str:
    raw = series.dropna().astype(str).str.strip()
    raw = raw[raw != ""]
    if raw.empty:
        return "unsupported"
    numeric = pd.to_numeric(raw, errors="coerce")
    if numeric.notna().all():
        unique_values = set(numeric.unique().tolist())
        if unique_values and unique_values <= {0, 1}:
            return "binary"
        return "numeric"
    unique_count = raw.nunique(dropna=True)
    if 2 <= unique_count <= 20:
        return "categorical"
    return "unsupported"


def valid_metric_values(series: pd.Series) -> pd.Series:
    values = series.dropna().astype(str).str.strip()
    return values[values != ""]


def chi_square_sf(x: float, k: int) -> float:
    if math.isnan(x) or k <= 0:
        return math.nan
    return gammaincc(k / 2.0, x / 2.0)


def gammaincc(a: float, x: float) -> float:
    if x < 0 or a <= 0:
        return math.nan
    if x == 0:
        return 1.0
    if x < a + 1.0:
        return max(0.0, 1.0 - gamma_p_series(a, x))
    return gamma_q_continued_fraction(a, x)


def gamma_p_series(a: float, x: float) -> float:
    gln = math.lgamma(a)
    ap = a
    summation = 1.0 / a
    delta = summation
    for _ in range(100):
        ap += 1
        delta *= x / ap
        summation += delta
        if abs(delta) < abs(summation) * 1e-12:
            break
    return summation * math.exp(-x + a * math.log(x) - gln)


def gamma_q_continued_fraction(a: float, x: float) -> float:
    gln = math.lgamma(a)
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, 101):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h * math.exp(-x + a * math.log(x) - gln)


def build_metric_note(metric_type: str, significant: bool, diff: float) -> str:
    if metric_type == "categorical":
        return "categorical metric: chi-square independence test at alpha=0.05"
    if significant and diff > 0:
        return f"{metric_type} metric: B is statistically higher than A at alpha=0.05"
    if significant and diff < 0:
        return f"{metric_type} metric: B is statistically lower than A at alpha=0.05"
    return f"{metric_type} metric: not statistically significant at alpha=0.05"


def metric_method(metric_type: str) -> tuple[str, str]:
    if metric_type == "binary":
        return (
            "Two-sample proportion z-test",
            "用于 0/1 二元指标，比较两组比例差异；当前为双侧检验，alpha=0.05。",
        )
    if metric_type == "unsupported":
        return (
            "Unsupported metric type",
            "当前支持 0/1 二元指标、连续数值指标和低基数类别指标；其他无法识别的因变量会保留在结果表中，但不生成 p 值、置信区间或图表。",
        )
    if metric_type == "categorical":
        return (
            "Chi-square test of independence",
            "用于类别型因变量，检验分组字段与类别分布是否独立；当前为 Pearson 卡方检验，alpha=0.05。",
        )
    return (
        "Welch-style mean difference test",
        "用于连续数值指标，比较两组均值差异；当前使用非等方差标准误与正态近似，alpha=0.05。",
    )


def f_sf(x: float, dfn: int, dfd: int) -> float:
    if math.isnan(x) or x < 0 or dfn <= 0 or dfd <= 0:
        return math.nan
    z = dfd / (dfd + dfn * x)
    return regularized_beta(z, dfd / 2.0, dfn / 2.0)


def regularized_beta(x: float, a: float, b: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - log_beta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * beta_continued_fraction(a, b, x) / a
    return 1.0 - front * beta_continued_fraction(b, a, 1.0 - x) / b


def beta_continued_fraction(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, 101):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def pct_value(value: float) -> str:
    if math.isnan(value):
        return ""
    return f"{value * 100:.2f}%"


def pp_value(value: float) -> str:
    if math.isnan(value):
        return ""
    return f"{value * 100:+.2f}pp"


def numeric_value(value: float) -> str:
    if math.isnan(value):
        return ""
    return f"{value:.4f}"


def signed_numeric_value(value: float) -> str:
    if math.isnan(value):
        return ""
    return f"{value:+.4f}"


def add_check(checks: list[dict[str, object]], name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})


def write_output(
    output_path: Path,
    validation_df: pd.DataFrame,
    sample_df: pd.DataFrame,
    metric_tests_df: pd.DataFrame,
    anova_df: pd.DataFrame,
    observation_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    conclusion_df: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        validation_df.to_excel(writer, sheet_name="data_quality_check", index=False)
        sample_df.to_excel(writer, sheet_name="sample_size", index=False)
        metric_tests_df.to_excel(writer, sheet_name="primary_metric_test", index=False)
        anova_df.to_excel(writer, sheet_name="anova_tests", index=False)
        observation_df.to_excel(writer, sheet_name="observation_metrics", index=False)
        segment_df.to_excel(writer, sheet_name="segment_diagnostics", index=False)
        conclusion_df.to_excel(writer, sheet_name="pm_conclusion", index=False)

        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            for col_cells in sheet.columns:
                max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col_cells)
                sheet.column_dimensions[col_cells[0].column_letter].width = min(max(max_len + 2, 12), 80)


def read_stage2_summary(output_path: Path) -> dict[str, object]:
    validation = pd.read_excel(output_path, sheet_name="data_quality_check").fillna("")
    sample_size = pd.read_excel(output_path, sheet_name="sample_size").fillna("")
    primary = pd.read_excel(output_path, sheet_name="primary_metric_test").fillna("")
    anova = pd.read_excel(output_path, sheet_name="anova_tests").fillna("")
    observation = pd.read_excel(output_path, sheet_name="observation_metrics").fillna("")
    segment = pd.read_excel(output_path, sheet_name="segment_diagnostics").fillna("")
    conclusion = pd.read_excel(output_path, sheet_name="pm_conclusion").fillna("")

    gate_rows = validation[validation["check"] == "overall_gate_status"]
    gate_status = str(gate_rows.iloc[0]["status"]) if not gate_rows.empty else "UNKNOWN"
    primary_row = primary.iloc[0].to_dict() if not primary.empty else {}
    warning_rows = validation[validation["status"] == "WARNING"]
    warnings = [
        {"check": str(row["check"]), "detail": str(row["detail"])}
        for _, row in warning_rows.iterrows()
    ]
    pm_rows = conclusion[conclusion["section"] == "pm_readable_conclusion"]
    pm_conclusion = str(pm_rows.iloc[0]["content"]) if not pm_rows.empty else ""

    return {
        "gate_status": gate_status,
        "warnings": warnings,
        "primary_metric": _clean_record(primary_row),
        "pm_conclusion": pm_conclusion,
        "tables": {
            "data_quality_check": _records(validation),
            "sample_size": _records(sample_size),
            "primary_metric_test": _records(primary),
            "anova_tests": _records(anova),
            "observation_metrics": _records(observation),
            "segment_diagnostics": _records(segment),
        },
    }


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [_clean_record(row) for row in frame.to_dict(orient="records")]


def _clean_record(record: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in record.items():
        if pd.isna(value):
            cleaned[key] = ""
        else:
            cleaned[key] = value
    return cleaned


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

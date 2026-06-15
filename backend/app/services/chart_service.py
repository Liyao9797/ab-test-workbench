import json
import re
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from app.core.paths import STORAGE_ROOT, ensure_storage_dirs


W, H = 1200, 760
BG = (248, 246, 240)
WHITE = (255, 255, 255)
TEXT = (23, 32, 38)
MUTED = (92, 107, 107)
GREEN = (32, 90, 89)
ORANGE = (201, 111, 59)
RED = (176, 64, 58)
BLUE = (61, 105, 152)
LINE = (213, 207, 196)


def generate_charts(job_id: str) -> dict[str, object]:
    ensure_storage_dirs()
    workbook_path = STORAGE_ROOT / "results" / job_id / "stage2_result.xlsx"
    if not workbook_path.exists():
        raise FileNotFoundError(f"Stage 2 workbook not found: {job_id}")

    data = pd.read_excel(workbook_path, sheet_name="primary_metric_test").fillna("")
    if data.empty:
        raise ValueError("Stage 2 workbook has no metric rows.")
    if len(data) > 5:
        raise ValueError("Chart generation supports at most 5 metric rows.")
    chartable_data, skipped_metrics = filter_chartable_metrics(data)

    chart_dir = STORAGE_ROOT / "charts" / job_id
    chart_dir.mkdir(parents=True, exist_ok=True)

    charts = []
    chart_paths: list[Path] = []
    for chart_index, (_, row) in enumerate(chartable_data.iterrows(), start=1):
        filename = f"metric_{chart_index}_{safe_name(str(row['metric']))}.png"
        render_metric_chart(row, chart_dir / filename)
        chart_paths.append(chart_dir / filename)
        charts.append(
            {
                "chart_id": f"metric_{chart_index}",
                "type": "metric",
                "metric": str(row["metric"]),
                "url": f"/api/charts/{job_id}/{filename}",
                "filename": filename,
            }
        )

    if not chartable_data.empty:
        summary_name = "summary.png"
        render_summary_chart(chartable_data, chart_dir / summary_name)
        chart_paths.append(chart_dir / summary_name)
        charts.append(
            {
                "chart_id": "summary",
                "type": "summary",
                "metric": None,
                "url": f"/api/charts/{job_id}/{summary_name}",
                "filename": summary_name,
            }
        )
        complete_name = "complete_all_charts.png"
        render_complete_chart_sheet(chart_paths, chart_dir / complete_name)
        charts.append(
            {
                "chart_id": "complete_all",
                "type": "complete",
                "metric": "all_charts",
                "url": f"/api/charts/{job_id}/{complete_name}",
                "filename": complete_name,
            }
        )

    manifest = {
        "job_id": job_id,
        "chart_count": len(charts),
        "max_chart_count": 7,
        "skipped_metrics": skipped_metrics,
        "charts": charts,
    }
    (chart_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def filter_chartable_metrics(data: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    rows = []
    skipped = []
    for _, row in data.iterrows():
        metric = str(row.get("metric", ""))
        if str(row.get("chartable", "YES")) == "NO":
            skipped.append({"metric": metric, "reason": str(row.get("note", "metric is not chartable"))})
            continue
        if str(row.get("metric_type", "")) == "categorical" and str(row.get("contingency_table", "")).strip():
            rows.append(row)
            continue
        try:
            parse_display_value(row.get("group_a_value", ""))
            parse_display_value(row.get("group_b_value", ""))
        except (TypeError, ValueError):
            skipped.append({"metric": metric, "reason": "A/B values are empty or non-numeric"})
            continue
        rows.append(row)
    return pd.DataFrame(rows), skipped


def render_metric_chart(row: pd.Series, output_path: Path) -> None:
    im, d = canvas(f"Metric: {row['metric']}", f"Type: {row['metric_type']} · Significant: {row['significant']}")
    if str(row.get("metric_type", "")) == "categorical":
        draw_categorical_chart(d, row)
        im.save(output_path)
        return
    a = parse_display_value(row["group_a_value"])
    b = parse_display_value(row["group_b_value"])
    maxv = max(a, b, 1.0 if "%" not in str(row["group_a_value"]) and "%" not in str(row["group_b_value"]) else 0.75)
    draw_bars(d, [str(row["group_a_label"]), str(row["group_b_label"])], [a, b], maxv)

    d.rounded_rectangle((730, 190, 1120, 560), radius=18, fill=WHITE, outline=LINE, width=2)
    details = [
        ("A value", str(row["group_a_value"])),
        ("B value", str(row["group_b_value"])),
        ("Diff", str(row["absolute_diff"])),
        ("Lift", str(row["relative_lift"])),
        ("p", str(row["p_value"])),
        ("95% CI", str(row["ci_95"])),
    ]
    y = 220
    for key, value in details:
        d.text((765, y), key, fill=MUTED, font=font(20))
        draw_right_fit_text(d, str(value), (1090, y), max_width=170, fill=TEXT, base_size=22, bold=True)
        y += 48

    note = str(row.get("note", ""))
    draw_fit_text(d, note, (72, 675), max_width=1040, fill=MUTED, base_size=20)
    im.save(output_path)


def draw_categorical_chart(d: ImageDraw.ImageDraw, row: pd.Series) -> None:
    table = json.loads(str(row.get("contingency_table", "{}")))
    groups = list(table.keys())
    categories = sorted({category for values in table.values() for category in values.keys()})
    if not groups or not categories:
        draw_fit_text(d, "No categorical distribution available", (90, 260), max_width=940, fill=MUTED, base_size=24)
        return

    x0, y0, x1, y1 = 95, 210, 680, 585
    d.line((x0, y1, x1, y1), fill=LINE, width=3)
    palette = [BLUE, GREEN, ORANGE, RED, (111, 95, 154), (87, 135, 105)]
    group_gap = (x1 - x0) / max(len(groups), 1)
    bar_w = min(52, max(24, int(group_gap / max(len(categories), 1) * 0.62)))
    max_rate = 1.0

    for group_index, group in enumerate(groups):
        values = table[group]
        total = sum(float(values.get(category, 0)) for category in categories) or 1.0
        center = x0 + group_gap * group_index + group_gap / 2
        start_x = center - (len(categories) * bar_w + (len(categories) - 1) * 8) / 2
        for category_index, category in enumerate(categories):
            rate = float(values.get(category, 0)) / total
            height = int((y1 - y0) * min(rate / max_rate, 1))
            bx0 = int(start_x + category_index * (bar_w + 8))
            by0 = y1 - height
            d.rounded_rectangle((bx0, by0, bx0 + bar_w, y1), radius=6, fill=palette[category_index % len(palette)])
            d.text((bx0 + bar_w / 2, by0 - 18), f"{rate * 100:.0f}%", fill=TEXT, font=font(14, True), anchor="mm")
        draw_centered_fit_text(d, group, int(center), y1 + 24, max_width=int(group_gap - 16), fill=TEXT, base_size=19)

    d.rounded_rectangle((730, 190, 1120, 560), radius=18, fill=WHITE, outline=LINE, width=2)
    d.text((765, 220), "p", fill=MUTED, font=font(20))
    draw_right_fit_text(d, str(row.get("p_value", "")), (1090, 220), max_width=150, fill=TEXT, base_size=22, bold=True)
    d.text((765, 268), "Chi-square", fill=MUTED, font=font(20))
    draw_right_fit_text(d, str(row.get("chi_square", "")), (1090, 268), max_width=150, fill=TEXT, base_size=22, bold=True)
    d.text((765, 316), "df", fill=MUTED, font=font(20))
    draw_right_fit_text(d, str(row.get("df", "")), (1090, 316), max_width=150, fill=TEXT, base_size=22, bold=True)
    d.text((765, 364), "Sig", fill=MUTED, font=font(20))
    draw_right_fit_text(d, str(row.get("significant", "")), (1090, 364), max_width=150, fill=TEXT, base_size=22, bold=True)

    legend_y = 430
    for index, category in enumerate(categories[:6]):
        y = legend_y + index * 22
        d.rounded_rectangle((765, y + 3, 779, y + 17), radius=3, fill=palette[index % len(palette)])
        draw_fit_text(d, category, (790, y), max_width=300, fill=TEXT, base_size=16)

    note = str(row.get("note", ""))
    draw_fit_text(d, note, (72, 675), max_width=1040, fill=MUTED, base_size=20)


def render_summary_chart(data: pd.DataFrame, output_path: Path) -> None:
    im, d = canvas("A/B Test Metric Summary", "One row per selected dependent variable")
    y = 165
    headers = ["Metric", "A", "B", "Diff", "p", "Sig"]
    xs = [70, 380, 520, 660, 810, 960]
    for x, header in zip(xs, headers):
        d.text((x, y), header, fill=MUTED, font=font(18, True))
    y += 42
    for _, row in data.iterrows():
        sig = str(row["significant"])
        fill = (231, 244, 236) if sig == "YES" else (255, 240, 205)
        outline = GREEN if sig == "YES" else ORANGE
        d.rounded_rectangle((52, y - 12, 1135, y + 42), radius=12, fill=fill, outline=outline, width=1)
        values = [
            str(row["metric"]),
            str(row["group_a_value"]),
            str(row["group_b_value"]),
            str(row["absolute_diff"]),
            str(row["p_value"]),
            sig,
        ]
        widths = [285, 115, 115, 125, 115, 110]
        for x, value, width in zip(xs, values, widths):
            draw_fit_text(d, value, (x, y), max_width=width, fill=TEXT, base_size=19, bold=value == sig)
        y += 68
    im.save(output_path)


def render_complete_chart_sheet(chart_paths: list[Path], output_path: Path) -> None:
    if not chart_paths:
        return
    thumb_w, thumb_h = 560, 355
    cols = 2
    rows = (len(chart_paths) + cols - 1) // cols
    margin = 48
    title_h = 92
    gap = 28
    sheet_w = margin * 2 + cols * thumb_w + (cols - 1) * gap
    sheet_h = margin + title_h + rows * thumb_h + max(rows - 1, 0) * gap + margin
    im = Image.new("RGB", (sheet_w, sheet_h), BG)
    d = ImageDraw.Draw(im)
    draw_fit_text(d, "Complete A/B Test Chart Pack", (margin, 34), max_width=sheet_w - margin * 2, fill=TEXT, base_size=34, bold=True)
    draw_fit_text(d, "Generated from all chartable Stage 2 metrics and the summary chart", (margin, 78), max_width=sheet_w - margin * 2, fill=MUTED, base_size=18)

    for index, path in enumerate(chart_paths):
        col = index % cols
        row = index // cols
        x = margin + col * (thumb_w + gap)
        y = margin + title_h + row * (thumb_h + gap)
        with Image.open(path) as source:
            source = source.convert("RGB")
            source.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            card = Image.new("RGB", (thumb_w, thumb_h), WHITE)
            px = (thumb_w - source.width) // 2
            py = (thumb_h - source.height) // 2
            card.paste(source, (px, py))
            im.paste(card, (x, y))
        d.rounded_rectangle((x, y, x + thumb_w, y + thumb_h), radius=14, outline=LINE, width=2)

    im.save(output_path)


def canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    draw_fit_text(d, title, (64, 42), max_width=1040, fill=TEXT, base_size=38, bold=True, min_size=26)
    draw_fit_text(d, subtitle, (66, 94), max_width=1040, fill=MUTED, base_size=21, min_size=16)
    return im, d


def draw_bars(d: ImageDraw.ImageDraw, labels: list[str], values: list[float], maxv: float) -> None:
    x0, y0, x1, y1 = 120, 210, 640, 585
    d.line((x0, y1, x1, y1), fill=LINE, width=3)
    bar_w = 118
    centers = [255, 505]
    colors = [BLUE, GREEN]
    for label, value, center, color in zip(labels, values, centers, colors):
        height = int((y1 - y0) * min(value / maxv, 1))
        bx0 = center - bar_w // 2
        by0 = y1 - height
        d.rounded_rectangle((bx0, by0, bx0 + bar_w, y1), radius=8, fill=color)
        d.text((center, by0 - 32), format_bar_value(value), fill=TEXT, font=font(22, True), anchor="mm")
        draw_centered_fit_text(d, label, center, y1 + 24, max_width=190, fill=TEXT, base_size=21)


def parse_display_value(value: object) -> float:
    text = str(value).strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    return float(text)


def format_bar_value(value: float) -> str:
    if value <= 1:
        return f"{value * 100:.1f}%"
    return f"{value:.2f}"


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")[:48] or "metric"


def draw_fit_text(
    d: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    fill: tuple[int, int, int],
    base_size: int,
    bold: bool = False,
    min_size: int = 13,
) -> None:
    text = normalize_text(text)
    size = base_size
    current_font = font(size, bold)
    while size > min_size and text_width(d, text, current_font) > max_width:
        size -= 1
        current_font = font(size, bold)
    if text_width(d, text, current_font) > max_width:
        text = ellipsize(d, text, current_font, max_width)
    d.text(xy, text, fill=fill, font=current_font)
    return text


def draw_right_fit_text(
    d: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    fill: tuple[int, int, int],
    base_size: int,
    bold: bool = False,
    min_size: int = 13,
) -> str:
    text = normalize_text(text)
    size = base_size
    current_font = font(size, bold)
    while size > min_size and text_width(d, text, current_font) > max_width:
        size -= 1
        current_font = font(size, bold)
    if text_width(d, text, current_font) > max_width:
        text = ellipsize(d, text, current_font, max_width)
    d.text(xy, text, fill=fill, font=current_font, anchor="ra")
    return text


def draw_centered_fit_text(
    d: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    y: int,
    max_width: int,
    fill: tuple[int, int, int],
    base_size: int,
) -> None:
    text = normalize_text(text)
    current_font = font(base_size)
    if text_width(d, text, current_font) > max_width:
        text = ellipsize(d, text, current_font, max_width)
    d.text((center_x, y), text, fill=fill, font=current_font, anchor="mt")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def ellipsize(d: ImageDraw.ImageDraw, text: str, current_font: ImageFont.ImageFont, max_width: int) -> str:
    if text_width(d, text, current_font) <= max_width:
        return text
    ellipsis = "..."
    available = max_width - text_width(d, ellipsis, current_font)
    if available <= 0:
        return ellipsis
    clipped = ""
    for char in text:
        if text_width(d, clipped + char, current_font) > available:
            break
        clipped += char
    return clipped.rstrip() + ellipsis


def text_width(d: ImageDraw.ImageDraw, text: str, current_font: ImageFont.ImageFont) -> int:
    bbox = d.textbbox((0, 0), text, font=current_font)
    return bbox[2] - bbox[0]


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

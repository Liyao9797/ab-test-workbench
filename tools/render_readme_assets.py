from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image, ImageDraw  # noqa: E402

from app.services.chart_service import (  # noqa: E402
    BG,
    BLUE,
    GREEN,
    LINE,
    MUTED,
    ORANGE,
    TEXT,
    WHITE,
    draw_centered_fit_text,
    draw_fit_text,
    draw_right_fit_text,
    font,
)


W, H = 1400, 900


def draw_status_badge(draw: ImageDraw.ImageDraw, text: str, center_x: int, center_y: int, color: tuple[int, int, int], fill: tuple[int, int, int]) -> None:
    badge_font = font(15, True)
    text_box = draw.textbbox((0, 0), text, font=badge_font)
    text_w = text_box[2] - text_box[0]
    badge_w = max(118, text_w + 34)
    badge_h = 30
    x0 = center_x - badge_w / 2
    x1 = center_x + badge_w / 2
    y0 = center_y - badge_h / 2
    y1 = center_y + badge_h / 2
    draw.rounded_rectangle((x0, y0, x1, y1), radius=8, fill=fill, outline=color, width=2)
    draw.text((center_x, center_y + 1), text, fill=color, font=badge_font, anchor="mm")


def fit_font_to_width(draw: ImageDraw.ImageDraw, text: str, max_width: int, base_size: int, bold: bool = False, min_size: int = 13):
    size = base_size
    current_font = font(size, bold)
    while size > min_size and draw.textbbox((0, 0), text, font=current_font)[2] > max_width:
        size -= 1
        current_font = font(size, bold)
    return current_font


def draw_centered_text_group(draw: ImageDraw.ImageDraw, lines: list[tuple[str, int, tuple[int, int, int], bool]], box: tuple[int, int, int, int], max_width: int, gap: int) -> None:
    center_x = (box[0] + box[2]) // 2
    center_y = (box[1] + box[3]) // 2
    fitted = []
    total_height = 0
    for text, size, fill, bold in lines:
        current_font = fit_font_to_width(draw, text, max_width, size, bold)
        bbox = draw.textbbox((0, 0), text, font=current_font)
        height = bbox[3] - bbox[1]
        fitted.append((text, current_font, fill, height))
        total_height += height
    total_height += gap * (len(fitted) - 1)
    y = center_y - total_height / 2
    for text, current_font, fill, height in fitted:
        draw.text((center_x, y + height / 2), text, fill=fill, font=current_font, anchor="mm")
        y += height + gap


def render_primary_metric(output_path: Path) -> None:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw_fit_text(draw, "Primary Metric: Feature Penetration Rate", (70, 52), 1260, TEXT, 42, bold=True)
    draw_fit_text(draw, "Read from Stage 2 workbook; significance is not recomputed", (72, 112), 1260, MUTED, 24)

    baseline_y = 700
    draw.line((220, baseline_y, 820, baseline_y), fill=LINE, width=3)
    bars = [
        ("group_a", 0.5, 370, BLUE),
        ("group_b", 0.6, 670, GREEN),
    ]
    max_value = 0.75
    for label, value, center, color in bars:
        height = int(380 * value / max_value)
        top = baseline_y - height
        draw.rounded_rectangle((center - 68, top, center + 68, baseline_y), radius=8, fill=color)
        draw.text((center, top - 34), f"{value * 100:.1f}%", fill=TEXT, font=font(24, True), anchor="mm")
        draw_centered_fit_text(draw, label, center, baseline_y + 24, 190, TEXT, 24)

    card = (880, 220, 1320, 700)
    draw.rounded_rectangle(card, radius=18, fill=WHITE, outline=(190, 205, 225), width=2)
    draw_fit_text(draw, "Stage 2 test result", (920, 265), 340, TEXT, 30, bold=True)

    rows = [
        ("Absolute lift", "+10.00pp"),
        ("Relative lift", "20.00%"),
        ("p-value", "0.004474"),
        ("95% CI", "[+3.14pp, +16.86pp]"),
        ("Decision", "Significant"),
    ]
    y = 340
    for label, value in rows:
        draw.text((920, y), label, fill=MUTED, font=font(24))
        value_color = GREEN if label == "Decision" else TEXT
        draw_right_fit_text(draw, value, (1295, y), max_width=210, fill=value_color, base_size=24, bold=True)
        y += 62

    draw_fit_text(
        draw,
        "B group feature penetration is statistically higher than A at alpha=0.05.",
        (70, 808),
        1260,
        TEXT,
        24,
    )
    image.save(output_path)


def render_data_quality_gate(output_path: Path) -> None:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw_fit_text(draw, "Data Quality Gate", (70, 48), 1260, TEXT, 44, bold=True)

    summary_box = (110, 130, 1290, 250)
    draw.rounded_rectangle(summary_box, radius=22, fill=(255, 249, 238), outline=(240, 85, 15), width=3)
    draw_centered_text_group(
        draw,
        [
            ("PASS_WITH_WARNING", 42, (240, 85, 15), True),
            ("Hard validation checks passed; warning items require PM attention.", 23, TEXT, False),
        ],
        summary_box,
        980,
        8,
    )

    checks = [
        ("PASS", "LT days >= login days", "violations=0"),
        ("PASS", "Click requires exposure", "violations=0"),
        ("PASS", "Inactive rows zeroed", "violations=0"),
        ("PASS", "D1 retention range", "A=63.75%, B=63.50%; target=60%-80%"),
        ("WARNING", "D7 retention range", "A=36.75%, B=37.50%; target=13%-22%"),
        ("PASS", "ARPU business cap", "A=1.24, B=1.33; max=3.00"),
        ("PASS", "LTV amount >= ARPU", "A ltv=2.02, arpu=1.24; B ltv=2.09, arpu=1.33"),
    ]

    table_x0, table_y0, table_x1 = 80, 295, 1320
    row_h = 58
    status_w = 175
    check_w = 390
    header_h = 46
    table_h = header_h + len(checks) * row_h
    draw.rounded_rectangle((table_x0, table_y0, table_x1, table_y0 + table_h), radius=16, fill=WHITE, outline=(220, 226, 232), width=2)
    draw.rectangle((table_x0 + 1, table_y0 + 1, table_x1 - 1, table_y0 + header_h), fill=(244, 247, 248))
    draw.text((table_x0 + 32, table_y0 + 14), "Status", fill=MUTED, font=font(18, True))
    draw.text((table_x0 + status_w + 28, table_y0 + 14), "Check", fill=MUTED, font=font(18, True))
    draw.text((table_x0 + status_w + check_w + 28, table_y0 + 14), "Result", fill=MUTED, font=font(18, True))

    for index, (status, check, result) in enumerate(checks):
        y = table_y0 + header_h + index * row_h
        if index:
            draw.line((table_x0, y, table_x1, y), fill=(229, 234, 238), width=1)
        is_warning = status == "WARNING"
        color = (240, 85, 15) if is_warning else (25, 170, 80)
        fill = (255, 248, 239) if is_warning else (239, 252, 244)
        row_center_y = y + row_h // 2
        draw_status_badge(draw, status, table_x0 + status_w // 2, row_center_y, color, fill)
        draw_fit_text(draw, check, (table_x0 + status_w + 28, row_center_y - 11), check_w - 48, TEXT, 20, bold=is_warning)
        draw_fit_text(draw, result, (table_x0 + status_w + check_w + 28, row_center_y - 11), 630, TEXT, 19)

    draw_fit_text(
        draw,
        "Primary metric conclusion remains tied to Stage 2; warnings are shown separately.",
        (70, 803),
        1260,
        TEXT,
        22,
    )
    image.save(output_path)


def render_segment_diagnostic(output_path: Path) -> None:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw_fit_text(draw, "Segment Diagnostic: New vs Old Users", (70, 52), 1260, TEXT, 42, bold=True)
    draw_fit_text(draw, "Diagnostic only; segment-level significance is not required", (72, 112), 1260, MUTED, 24)

    baseline_y = 700
    draw.line((160, baseline_y, 1240, baseline_y), fill=LINE, width=3)
    groups = [
        ("New users", [("A", 0.51, BLUE), ("B", 0.575, GREEN)], "+6.50pp", 380),
        ("Old users", [("A", 0.49, BLUE), ("B", 0.625, GREEN)], "+13.50pp", 900),
    ]
    max_value = 0.75
    for group_label, bars, lift, center in groups:
        for offset, (bar_label, value, color) in zip((-75, 75), bars):
            x = center + offset
            height = int(380 * value / max_value)
            top = baseline_y - height
            draw.rounded_rectangle((x - 60, top, x + 60, baseline_y), radius=8, fill=color)
            draw.text((x, top - 32), f"{value * 100:.1f}%", fill=TEXT, font=font(22, True), anchor="mm")
            draw_centered_fit_text(draw, bar_label, x, baseline_y + 22, 120, TEXT, 22)
        draw_centered_fit_text(draw, group_label, center, 768, 260, TEXT, 28)
        draw_centered_fit_text(draw, f"Lift: {lift}", center, 820, 260, (0, 160, 70), 22)

    draw_fit_text(
        draw,
        "Direction check: B > A in both new-user and old-user segments.",
        (70, 842),
        1260,
        TEXT,
        22,
    )
    image.save(output_path)


def main() -> None:
    targets = [
        (ROOT / "docs/assets/readme/primary-metric.png", render_primary_metric),
        (ROOT / "docs/assets/readme/data-quality-gate.png", render_data_quality_gate),
        (ROOT / "stage3_ab_charts_scripted/01_primary_feature_penetration.png", render_primary_metric),
        (ROOT / "stage3_ab_charts_scripted/02_segment_feature_penetration.png", render_segment_diagnostic),
        (ROOT / "stage3_ab_charts_scripted/04_data_quality_gate.png", render_data_quality_gate),
        (ROOT / "stage3_ab_charts/01_primary_feature_penetration.png", render_primary_metric),
        (ROOT / "stage3_ab_charts/02_segment_feature_penetration.png", render_segment_diagnostic),
        (ROOT / "stage3_ab_charts/04_data_quality_gate.png", render_data_quality_gate),
        (ROOT / "e2e_acceptance/stage3_png/02_segment_feature_penetration.png", render_segment_diagnostic),
        (ROOT / "small_case/stage3_png/02_segment_feature_penetration.png", render_segment_diagnostic),
        (ROOT / "small_case_low_lift/stage3_png/02_segment_feature_penetration.png", render_segment_diagnostic),
    ]
    for path, renderer in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        renderer(path)
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()

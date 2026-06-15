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

    draw_fit_text(draw, "Data Quality Gate", (70, 52), 1260, TEXT, 44, bold=True)
    draw_fit_text(draw, "Overall status: PASS_WITH_WARNING", (72, 122), 1260, MUTED, 26)

    draw.rounded_rectangle((90, 210, 1310, 395), radius=28, fill=(255, 249, 238), outline=(240, 85, 15), width=4)
    draw_fit_text(draw, "PASS_WITH_WARNING", (140, 270), 1060, (240, 85, 15), 48, bold=True)
    draw_fit_text(
        draw,
        "Hard validation checks passed; warning items require PM attention.",
        (140, 345),
        1080,
        TEXT,
        26,
    )

    checks = [
        ("PASS", "lt_days_gte_login_days: violations=0"),
        ("PASS", "feature_click_requires_exposure: violations=0"),
        ("PASS", "inactive_rows_zeroed: violations=0"),
        ("PASS", "d1_retention_business_range: group_a=63.75%, group_b=63.50%; expected=60%-80%"),
        ("WARNING", "d7_retention_business_range: group_a=36.75%, group_b=37.50%; expected=13%-22%"),
        ("PASS", "arpu_business_cap: group_a=1.24, group_b=1.33; max=3.00"),
        ("PASS", "avg_ltv_amount_gte_arpu: group_a ltv=2.02, arpu=1.24; group_b ltv=2.09, arpu=1.33"),
    ]

    y = 465
    row_gap = 56
    for status, message in checks:
        is_warning = status == "WARNING"
        color = (240, 85, 15) if is_warning else (25, 170, 80)
        fill = (255, 248, 239) if is_warning else (239, 252, 244)
        draw.rounded_rectangle((105, y, 265, y + 44), radius=10, fill=fill, outline=color, width=2)
        draw.text((185, y + 22), status, fill=color, font=font(22, True), anchor="mm")
        draw_fit_text(draw, message, (315, y + 8), 940, TEXT, 21)
        y += row_gap

    draw_fit_text(
        draw,
        "Primary metric conclusion remains tied to Stage 2; warnings are shown separately.",
        (70, 862),
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

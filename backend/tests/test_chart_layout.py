from PIL import Image, ImageDraw

from app.services.chart_service import TEXT, draw_right_fit_text, font, text_width


def test_draw_right_fit_text_keeps_long_ci_inside_bounds():
    image = Image.new("RGB", (360, 120), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    text = "[+3.14pp, +16.86pp]"
    right_x = 330
    max_width = 120

    rendered = draw_right_fit_text(
        draw,
        text,
        (right_x, 30),
        max_width=max_width,
        fill=TEXT,
        base_size=22,
        bold=True,
    )

    assert text_width(draw, rendered, font(13, True)) <= max_width
    bbox = draw.textbbox((right_x, 30), rendered, font(13, True), anchor="ra")
    assert bbox[0] >= right_x - max_width
    assert bbox[2] <= right_x

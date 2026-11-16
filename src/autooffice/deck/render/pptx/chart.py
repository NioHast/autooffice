"""Integrasi chart native dan placeholder untuk renderer PPTX AutoOffice."""

from typing import cast

from pptx.chart.data import ChartData
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.charts.native import (
    build_category_chart_data,
    format_native_chart,
    native_chart_type,
    validate_native_chart,
)
from autooffice.deck.charts.placeholder import (
    CHART_MARKER_PREFIX,
    chart_marker,
    chart_placeholder_id,
    create_chart_placeholder,
    find_chart_placeholders,
    parse_chart_marker,
)
from autooffice.deck.charts.spec import ChartSpec
from autooffice.design.theme import Theme

__all__ = [
    "CHART_MARKER_PREFIX",
    "add_chart_placeholder",
    "add_native_chart",
    "chart_id_from_shape",
    "chart_marker",
    "find_chart_placeholders",
    "render_chart",
]


def add_native_chart(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
) -> GraphicFrame:
    """Tambahkan satu chart native pada box block dan kembalikan frame-nya."""
    data = build_category_chart_data(spec)
    result = slide.shapes.add_chart(
        native_chart_type(spec),
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(height),
        cast(ChartData, data),
    )
    frame = cast(GraphicFrame, result)
    frame.name = chart_marker(spec.chart_id)
    c_nv_pr = frame._element.nvGraphicFramePr.cNvPr
    c_nv_pr.set("title", spec.chart_id)
    c_nv_pr.set("descr", spec.alt)
    format_native_chart(frame.chart, spec, theme)
    validate_native_chart(frame.chart, spec)
    return frame


def add_chart_placeholder(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
) -> Shape:
    """Tambahkan placeholder chart pada box block untuk staging Slides."""
    shape = create_chart_placeholder(
        slide,
        spec,
        theme,
        left=left,
        top=top,
        width=width,
        height=height,
    )
    return shape


def render_chart(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    placeholder: bool = False,
) -> GraphicFrame | Shape:
    """Render chart pada box block, native atau placeholder."""
    if placeholder:
        return add_chart_placeholder(
            slide,
            spec,
            theme,
            left=left,
            top=top,
            width=width,
            height=height,
        )
    return add_native_chart(
        slide,
        spec,
        theme,
        left=left,
        top=top,
        width=width,
        height=height,
    )


def chart_id_from_shape(shape: BaseShape) -> str | None:
    """Baca ``chart_id`` dari chart native atau placeholder, bila ada."""
    if isinstance(shape, GraphicFrame) and shape.has_chart:
        return parse_chart_marker(shape.name)
    if isinstance(shape, Shape):
        return chart_placeholder_id(shape)
    return None

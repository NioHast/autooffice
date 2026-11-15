"""Tes cabang edge chart identity."""

from _edge_helpers import new_slide
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.util import Emu

from autooffice.deck.charts.spec import build_chart_spec
from autooffice.deck.render.pptx.chart import (
    add_chart_placeholder,
    add_native_chart,
    chart_id_from_shape,
)


def _chart_spec(chart_case):
    return build_chart_spec(chart_case.deck.slides[0].blocks[0], slide_id="s01")


def _add_chart(slide, spec, theme, *, placeholder: bool):
    add = add_chart_placeholder if placeholder else add_native_chart
    return add(
        slide,
        spec,
        theme,
        left=914400,
        top=609600,
        width=4_000_000,
        height=3_000_000,
    )


def test_chart_id_from_shape_reads_native_chart(chart_case, theme) -> None:
    shape = _add_chart(new_slide(), _chart_spec(chart_case), theme, placeholder=False)

    assert chart_id_from_shape(shape) == "s01.chart1"


def test_chart_id_from_shape_reads_placeholder(chart_case, theme) -> None:
    shape = _add_chart(new_slide(), _chart_spec(chart_case), theme, placeholder=True)

    assert chart_id_from_shape(shape) == "s01.chart1"


def test_chart_id_from_shape_returns_none_for_non_chart_shape() -> None:
    connector = new_slide().shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Emu(0),
        Emu(0),
        Emu(100000),
        Emu(100000),
    )

    assert chart_id_from_shape(connector) is None

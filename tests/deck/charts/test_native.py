"""Test chart native PPTX: part, data, metadata, warna, dan format theme."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.shapes.graphfrm import GraphicFrame
from pptx.slide import Slide

from autooffice.deck.charts import (
    ChartSpec,
    ChartSpecError,
    chart_marker,
    native_chart_type,
    validate_native_chart,
)
from autooffice.deck.model import ChartSeries
from autooffice.deck.render.pptx.chart import add_native_chart
from autooffice.design.contrast import contrast_ratio
from autooffice.design.theme import Theme

_CHART_IDS = ("s01.chart1", "s02.chart1", "s03.chart1", "s04.chart1")


def _rgb(value: object) -> str:
    return f"#{value}"


def _add(
    slide: Slide,
    spec: ChartSpec,
    theme: Theme,
    chart_box: Mapping[str, int],
) -> GraphicFrame:
    return add_native_chart(slide, spec, theme, **chart_box)


@pytest.mark.parametrize(
    ("chart_id", "expected"),
    [
        ("s01.chart1", XL_CHART_TYPE.COLUMN_CLUSTERED),
        ("s02.chart1", XL_CHART_TYPE.BAR_CLUSTERED),
        ("s03.chart1", XL_CHART_TYPE.LINE_MARKERS),
        ("s04.chart1", XL_CHART_TYPE.DOUGHNUT),
    ],
)
def test_native_chart_type(
    chart_id: str,
    expected: XL_CHART_TYPE,
    chart_specs: Mapping[str, ChartSpec],
) -> None:
    assert native_chart_type(chart_specs[chart_id]) == expected


@pytest.mark.parametrize("chart_id", _CHART_IDS)
def test_native_chart_parts_have_no_image(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    presentation: Presentation,
    chart_box: Mapping[str, int],
    tmp_path: Path,
) -> None:
    frame = _add(slide, chart_specs[chart_id], theme, chart_box)
    output = tmp_path / "chart.pptx"
    presentation.save(output)

    assert frame.has_chart is True
    assert frame.shape_type == MSO_SHAPE_TYPE.CHART
    assert not any(
        shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in presentation.slides[0].shapes
    )

    loaded = Presentation(output)
    loaded_frame = loaded.slides[0].shapes[0]
    assert isinstance(loaded_frame, GraphicFrame)
    assert loaded_frame.has_chart is True
    part_names = {str(part.partname) for part in loaded.part.package.iter_parts()}
    assert any(name.startswith("/ppt/charts/chart") for name in part_names)
    assert any(name.startswith("/ppt/embeddings/") for name in part_names)
    assert not any(name.startswith("/ppt/media/") for name in part_names)


@pytest.mark.parametrize("chart_id", _CHART_IDS)
def test_categories_and_series_match_spec(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs[chart_id]
    frame = _add(slide, spec, theme, chart_box)
    chart = frame.chart

    assert tuple(str(category) for category in chart.plots[0].categories) == spec.categories
    assert tuple(str(series.name) for series in chart.series) == tuple(
        series.name for series in spec.series
    )
    assert tuple(
        tuple(float(value) for value in series.values) for series in chart.series
    ) == tuple(tuple(float(value) for value in series.values) for series in spec.series)
    validate_native_chart(chart, spec)


def test_native_chart_metadata_is_deterministic(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    c_nv_pr = frame._element.nvGraphicFramePr.cNvPr

    assert frame.name == chart_marker(spec.chart_id)
    assert c_nv_pr.get("title") == spec.chart_id
    assert c_nv_pr.get("descr") == spec.alt
    assert frame.chart.has_title is True
    assert frame.chart.chart_title.text_frame.text == spec.title


@pytest.mark.parametrize("chart_id", ["s01.chart1", "s03.chart1"])
def test_bar_and_line_series_use_four_theme_colors(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs[chart_id]
    frame = _add(slide, spec, theme, chart_box)
    chart = frame.chart

    if spec.kind == "bar":
        actual = tuple(_rgb(series.format.fill.fore_color.rgb) for series in chart.series)
    else:
        actual = tuple(_rgb(series.format.line.color.rgb) for series in chart.series)

    assert actual == theme.chart.series[: len(spec.series)]


def test_donut_categories_use_theme_series_colors(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s04.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    series = frame.chart.series[0]

    actual = tuple(_rgb(series.points[index].format.fill.fore_color.rgb) for index in range(4))

    assert actual == theme.chart.series


def test_chart_font_legend_gridlines_and_axis_come_from_theme(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s01.chart1"], theme, chart_box)
    chart = frame.chart

    assert chart.font.name == theme.typography.family
    assert chart.has_legend is True
    assert chart.legend.font.name == theme.typography.family
    assert _rgb(chart.legend.font.color.rgb) == theme.chart.legend
    assert chart.value_axis.has_major_gridlines is True
    assert _rgb(chart.value_axis.major_gridlines.format.line.color.rgb) == theme.chart.grid
    assert _rgb(chart.value_axis.format.line.color.rgb) == theme.chart.axis
    assert _rgb(chart.value_axis.tick_labels.font.color.rgb) == theme.chart.axis
    title_font = chart.chart_title.text_frame.paragraphs[0].font
    assert title_font.name == theme.typography.family
    assert title_font.bold is True
    assert title_font.size is not None
    assert title_font.size.pt == theme.typography.label_pt
    assert _rgb(title_font.color.rgb) == theme.chart.title
    assert chart.value_axis.major_gridlines.format.line.width is not None
    assert chart.value_axis.major_gridlines.format.line.width.pt == 1.0


@pytest.mark.parametrize("chart_id", _CHART_IDS)
def test_bar_line_and_donut_show_data_labels(
    chart_id: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs[chart_id], theme, chart_box)
    spec = chart_specs[chart_id]
    if spec.kind == "line":
        for series in frame.chart.series:
            assert series.data_labels.show_value is False
            d_lbls = series.data_labels._element
            d_lbl = d_lbls.find(qn("c:dLbl"))
            assert d_lbl is not None
            assert d_lbl.find(qn("c:showVal")).get("val") == "1"
            assert series.data_labels.font.size is not None
            assert series.data_labels.font.size.pt == theme.typography.minimum_pt
            assert _rgb(series.data_labels.font.color.rgb) == theme.chart.axis
        return
    plot = frame.chart.plots[0]

    assert plot.has_data_labels is True
    assert plot.data_labels.show_value is True
    assert plot.data_labels.font.size is not None
    assert plot.data_labels.font.size.pt == theme.typography.minimum_pt
    expected_color = theme.colors.accent_ink if spec.kind == "donut" else theme.chart.axis
    assert _rgb(plot.data_labels.font.color.rgb) == expected_color


@pytest.mark.parametrize(
    ("chart_id", "position"),
    [
        ("s01.chart1", "outEnd"),
        ("s02.chart1", "outEnd"),
    ],
)
def test_bar_data_labels_have_explicit_axis_position(
    chart_id: str,
    position: str,
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs[chart_id], theme, chart_box)
    d_lbls = frame.chart.plots[0].data_labels._element
    d_lbl_pos = d_lbls.find(qn("c:dLblPos"))

    assert d_lbl_pos is not None
    assert d_lbl_pos.get("val") == position


def test_line_labels_only_on_last_point(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s03.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    last_index = len(spec.categories) - 1
    positions: list[str | None] = []

    for series in frame.chart.series:
        d_lbls = series.data_labels._element
        d_lbls_for_point = d_lbls.findall(qn("c:dLbl"))
        assert len(d_lbls_for_point) == 1
        d_lbl = d_lbls_for_point[0]
        assert d_lbl.find(qn("c:idx")).get("val") == str(last_index)
        assert d_lbl.find(qn("c:showVal")).get("val") == "1"
        d_lbl_pos = d_lbl.find(qn("c:dLblPos"))
        assert d_lbl_pos is not None
        positions.append(d_lbl_pos.get("val"))

    assert positions == ["t", "b"]


def test_donut_has_no_dlblpos(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s04.chart1"], theme, chart_box)
    d_lbls = frame.chart.plots[0].data_labels._element

    assert d_lbls.find(qn("c:dLblPos")) is None


def test_donut_labels_have_leader_lines(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s04.chart1"], theme, chart_box)
    d_lbls = frame.chart.plots[0].data_labels._element
    leader_lines = d_lbls.find(qn("c:showLeaderLines"))

    assert leader_lines is not None
    assert leader_lines.get("val") == "1"


def test_donut_label_color_contrasts_with_every_slice(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s04.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    label_color = _rgb(frame.chart.plots[0].data_labels.font.color.rgb)
    slice_colors = theme.chart.series[: len(spec.categories)]

    assert label_color == theme.colors.accent_ink
    for slice_color in slice_colors:
        assert contrast_ratio(label_color, slice_color) >= 4.5


def test_single_series_bar_and_donut_legend_rules(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    bar = _add(slide, chart_specs["s02.chart1"], theme, chart_box)
    donut = _add(slide, chart_specs["s04.chart1"], theme, chart_box)

    assert bar.chart.has_legend is False
    assert donut.chart.has_legend is True


def test_line_markers_and_unit_axis(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s03.chart1"], theme, chart_box)
    chart = frame.chart

    assert all(series.marker.style == XL_MARKER_STYLE.CIRCLE for series in chart.series)
    assert all(series.marker.size == 6 for series in chart.series)
    assert chart.value_axis.has_title is True
    assert chart.value_axis.axis_title.text_frame.text == "persen"


def test_validation_rejects_wrong_chart_spec(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    frame = _add(slide, chart_specs["s01.chart1"], theme, chart_box)

    with pytest.raises(ChartSpecError, match="seharusnya"):
        validate_native_chart(frame.chart, chart_specs["s03.chart1"])


def test_validation_rejects_category_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    wrong = replace(spec, categories=("X1", "X2", "X3", "X4"))

    with pytest.raises(ChartSpecError, match="Kategori"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_series_count_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    wrong = replace(spec, series=spec.series[:1])

    with pytest.raises(ChartSpecError, match="memiliki 4 seri"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_series_name_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    first = spec.series[0]
    wrong = replace(
        spec,
        series=(ChartSeries(name="Lain", values=first.values), *spec.series[1:]),
    )

    with pytest.raises(ChartSpecError, match="bernama"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_series_value_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    first = spec.series[0]
    wrong = replace(
        spec,
        series=(ChartSeries(name=first.name, values=(0, 0, 0, 0)), *spec.series[1:]),
    )

    with pytest.raises(ChartSpecError, match="Nilai seri"):
        validate_native_chart(frame.chart, wrong)


def test_validation_rejects_title_mismatch(
    chart_specs: Mapping[str, ChartSpec],
    theme: Theme,
    slide: Slide,
    chart_box: Mapping[str, int],
) -> None:
    spec = chart_specs["s01.chart1"]
    frame = _add(slide, spec, theme, chart_box)
    wrong = replace(spec, title="Judul lain")

    with pytest.raises(ChartSpecError, match="Title chart"):
        validate_native_chart(frame.chart, wrong)

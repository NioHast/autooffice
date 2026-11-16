"""Pembentuk chart native python-pptx dari ``ChartSpec`` dan ``Theme``."""

from pptx.chart.chart import Chart
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_MARKER_STYLE,
)
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.text.text import Font
from pptx.util import Pt

from autooffice.design.theme import Theme

from .colors import chart_category_colors, chart_element_color, chart_series_colors
from .spec import ChartSpec, ChartSpecError

# Marker line sengaja memakai 6 pt sebagai konstanta renderer, bukan token
# theme: hanya chart line yang memakai marker dan tidak ada varian ukuran lain.
_LINE_MARKER_SIZE = 6
_EMU_PER_POINT = 12700


def build_category_chart_data(spec: ChartSpec) -> CategoryChartData:
    """Bangun data kategori native yang akan ditanam sebagai workbook PPTX."""
    data = CategoryChartData()  # type: ignore[no-untyped-call]
    data.categories = list(spec.categories)
    for series in spec.series:
        data.add_series(series.name, list(series.values))  # type: ignore[no-untyped-call]
    return data


def native_chart_type(spec: ChartSpec) -> XL_CHART_TYPE:
    """Pilih tipe chart native sesuai kind dan orientation."""
    if spec.kind == "bar":
        if spec.orientation == "horizontal":
            return XL_CHART_TYPE.BAR_CLUSTERED
        return XL_CHART_TYPE.COLUMN_CLUSTERED
    if spec.kind == "line":
        return XL_CHART_TYPE.LINE_MARKERS
    return XL_CHART_TYPE.DOUGHNUT


def format_native_chart(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    """Terapkan title, legend, axis, gridline, label, font, dan warna token."""
    chart.font.name = theme.typography.family
    chart.font.size = Pt(theme.typography.minimum_pt)
    chart.font.color.rgb = chart_element_color(theme, "axis")
    _format_title(chart, spec, theme)
    _format_legend(chart, spec, theme)
    if spec.kind == "donut":
        _format_labels(chart, spec, theme)
        _format_donut_series(chart, spec, theme)
        return
    _format_axes(chart, spec, theme)
    _format_category_series(chart, spec, theme)
    _format_labels(chart, spec, theme)


def validate_native_chart(chart: Chart, spec: ChartSpec) -> None:
    """Pastikan chart native memuat tipe, data, dan title sesuai spec."""
    expected_type = native_chart_type(spec)
    if chart.chart_type != expected_type:
        raise ChartSpecError(
            f"Chart '{spec.chart_id}' bertipe {chart.chart_type}, seharusnya {expected_type}."
        )
    actual_categories = tuple(str(category) for category in chart.plots[0].categories)
    if actual_categories != spec.categories:
        raise ChartSpecError(
            f"Kategori chart '{spec.chart_id}' tidak cocok: "
            f"{actual_categories!r} != {spec.categories!r}."
        )
    actual_series = tuple(chart.series)
    if len(actual_series) != len(spec.series):
        raise ChartSpecError(
            f"Chart '{spec.chart_id}' memiliki {len(actual_series)} seri, "
            f"seharusnya {len(spec.series)}."
        )
    for index, (actual, expected) in enumerate(zip(actual_series, spec.series, strict=True)):
        if str(actual.name) != expected.name:
            raise ChartSpecError(
                f"Seri {index} chart '{spec.chart_id}' bernama '{actual.name}', "
                f"seharusnya '{expected.name}'."
            )
        actual_values = tuple(float(value) for value in actual.values)
        expected_values = tuple(float(value) for value in expected.values)
        if actual_values != expected_values:
            raise ChartSpecError(
                f"Nilai seri '{expected.name}' chart '{spec.chart_id}' tidak cocok."
            )
    if spec.title:
        if not chart.has_title or chart.chart_title.text_frame.text != spec.title:
            raise ChartSpecError(f"Title chart '{spec.chart_id}' tidak cocok dengan spec.")
    elif chart.has_title and chart.chart_title.text_frame.text.strip():
        raise ChartSpecError(f"Chart '{spec.chart_id}' memiliki title walau spec tidak memintanya.")


def _format_title(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    if not spec.title.strip():
        chart.has_title = False
        return
    chart.has_title = True
    text_frame = chart.chart_title.text_frame
    text_frame.text = spec.title
    _apply_font(
        text_frame.paragraphs[0].font,
        theme=theme,
        size_pt=theme.typography.label_pt,
        color=chart_element_color(theme, "title"),
        bold=True,
    )


def _format_legend(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    visible = spec.kind == "donut" or len(spec.series) > 1
    chart.has_legend = visible
    if not visible:
        return
    legend = chart.legend
    legend.position = XL_LEGEND_POSITION.RIGHT
    legend.include_in_layout = False
    _apply_font(
        legend.font,
        theme=theme,
        size_pt=theme.typography.minimum_pt,
        color=chart_element_color(theme, "legend"),
    )


def _format_axes(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    category_axis = chart.category_axis
    value_axis = chart.value_axis
    line_width = Pt(theme.spacing.divider_emu / _EMU_PER_POINT)
    for axis in (category_axis, value_axis):
        axis.format.line.color.rgb = chart_element_color(theme, "axis")
        axis.format.line.width = line_width
        _apply_font(
            axis.tick_labels.font,
            theme=theme,
            size_pt=theme.typography.minimum_pt,
            color=chart_element_color(theme, "axis"),
        )
    category_axis.has_major_gridlines = False
    value_axis.has_major_gridlines = True
    value_axis.major_gridlines.format.line.color.rgb = chart_element_color(theme, "grid")
    value_axis.major_gridlines.format.line.width = line_width
    if spec.unit is not None:
        value_axis.has_title = True
        value_axis.axis_title.text_frame.text = spec.unit
        _apply_font(
            value_axis.axis_title.text_frame.paragraphs[0].font,
            theme=theme,
            size_pt=theme.typography.minimum_pt,
            color=chart_element_color(theme, "axis"),
        )


def _format_labels(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    """Tampilkan data label nilai pada bar, line, dan donut.

    Donut tidak memakai ``c:dLblPos`` karena elemen itu tidak didukung untuk
    doughnut dan membuat PowerPoint menolak berkas. Label donut memakai posisi
    default PowerPoint (di dalam slice) dengan teks putih; semua warna slice
    theme lolos kontras minimal 4,5:1 terhadap putih. Bar memakai ``outEnd``.
    Line hanya memberi label pada titik terakhir tiap seri, bergantian di atas
    dan di bawah, karena posisi seragam untuk semua titik tetap tumpang tindih
    pada data demo.
    """
    if spec.kind == "line":
        _format_line_labels(chart, spec, theme)
        return
    plot = chart.plots[0]
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.show_value = True
    labels.show_category_name = False
    labels.show_series_name = False
    labels.show_legend_key = False
    if spec.kind == "donut":
        # Tidak ada dLblPos untuk doughnut. Pertahankan leader line di XML
        # agar perilakunya eksplisit walau label default berada di dalam slice.
        d_lbls = labels._element
        if d_lbls.find(qn("c:showLeaderLines")) is None:
            leader_lines = OxmlElement("c:showLeaderLines")
            leader_lines.set("val", "1")
            d_lbls.insert_element_before(leader_lines, "c:leaderLines", "c:extLst")
        label_color = RGBColor.from_string(  # type: ignore[no-untyped-call]
            theme.colors.accent_ink[1:]
        )
    else:
        labels.position = XL_LABEL_POSITION.OUTSIDE_END
        label_color = chart_element_color(theme, "axis")
    _apply_font(
        labels.font,
        theme=theme,
        size_pt=theme.typography.minimum_pt,
        color=label_color,
    )


def _format_line_labels(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    """Beri label hanya pada titik terakhir tiap seri line.

    Label semua titik membuat dua seri yang berdekatan bertumpuk selebar label
    (sekitar 1,2-2,7 pt) pada posisi above, right, maupun below. Dengan satu
    label terakhir per seri dan posisi bergantian atas/bawah, kepadatan turun
    dari 16 menjadi 2 label dan tidak ada pasangan yang bertumpuk.
    """
    for series_index, series in enumerate(chart.series):
        series_labels = series.data_labels
        series_labels.show_value = False
        series_labels.show_category_name = False
        series_labels.show_series_name = False
        series_labels.show_legend_key = False
        _apply_font(
            series_labels.font,
            theme=theme,
            size_pt=theme.typography.minimum_pt,
            color=chart_element_color(theme, "axis"),
        )
        last_index = len(spec.series[series_index].values) - 1
        d_lbl = series_labels._element.get_or_add_dLbl_for_point(last_index)
        d_lbl.get_or_add_dLblPos().val = (
            XL_LABEL_POSITION.ABOVE if series_index % 2 == 0 else XL_LABEL_POSITION.BELOW
        )


def _format_category_series(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    colors = chart_series_colors(theme, len(spec.series))
    for series, color in zip(chart.series, colors, strict=True):
        if spec.kind == "line":
            series.format.line.color.rgb = color
            series.smooth = False
            series.marker.style = XL_MARKER_STYLE.CIRCLE
            series.marker.size = _LINE_MARKER_SIZE
            series.marker.format.fill.solid()
            series.marker.format.fill.fore_color.rgb = color
            series.marker.format.line.color.rgb = color
            continue
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
        series.format.line.color.rgb = color


def _format_donut_series(chart: Chart, spec: ChartSpec, theme: Theme) -> None:
    colors = chart_category_colors(theme, len(spec.categories))
    series = chart.series[0]
    for index, color in enumerate(colors):
        point = series.points[index]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = color


def _apply_font(
    font: Font,
    *,
    theme: Theme,
    size_pt: float,
    color: RGBColor,
    bold: bool = False,
) -> None:
    font.name = theme.typography.family
    font.size = Pt(size_pt)
    font.bold = bold
    font.color.rgb = color


__all__ = [
    "build_category_chart_data",
    "format_native_chart",
    "native_chart_type",
    "validate_native_chart",
]

"""Render block diagram PlantUML sebagai picture native di slide PPTX."""

from pathlib import Path

from pptx.enum.shapes import MSO_SHAPE
from pptx.shapes.base import BaseShape
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.media.plantuml import (
    PlantUmlError,
    render_plantuml,
    resolve_plantuml_source,
)
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

from .image import contain_geometry, image_size
from .shapes import (
    DIAGRAM_MARKER,
    Box,
    PptxRenderError,
    field_optional_text,
    field_text,
    rgb,
    set_chrome_shape,
    set_namespace_marker,
)

CACHE_DIR = Path("cache") / "plantuml"


def render_diagram_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
    workspace: Path,
) -> tuple[BaseShape, ...]:
    """Render satu block diagram dan kembalikan picture-nya.

    Diagram selalu menjadi gambar PNG hasil ``plantuml``; tidak ada fallback teks
    atau shape. Bila render gagal, error dari modul media diteruskan sebagai
    ``PptxRenderError`` dengan konteks slide dan block.
    """
    relative_source = field_text(block.fields, "source", block_id=block.block_id)
    alt = field_optional_text(block.fields, "alt")
    cache_dir = workspace / CACHE_DIR
    output = cache_dir / f"{slide_id}.{block.block_id}.png"
    try:
        source = resolve_plantuml_source(workspace, relative_source)
        png = render_plantuml(source, output, theme=theme, cache_dir=cache_dir)
    except PlantUmlError as error:
        raise PptxRenderError(
            f"Slide '{slide_id}', block '{block.block_id}' gagal merender diagram PlantUML: {error}"
        ) from error

    image_width, image_height = image_size(png)
    geometry = contain_geometry(image_width, image_height, box)
    frame = _add_diagram_frame(slide, geometry, theme, namespace=f"{slide_id}.{block.block_id}")
    picture = slide.shapes.add_picture(
        str(png),
        left=Emu(geometry[0]),
        top=Emu(geometry[1]),
        width=Emu(geometry[2]),
        height=Emu(geometry[3]),
    )
    set_namespace_marker(
        picture,
        DIAGRAM_MARKER,
        f"{slide_id}.{block.block_id}",
        description=alt,
    )
    return (frame, picture)


def _add_diagram_frame(
    slide: Slide,
    geometry: tuple[int, int, int, int],
    theme: Theme,
    *,
    namespace: str,
) -> BaseShape:
    """Gambar hairline di tepi geometry picture supaya diagram putih tetap terlihat."""
    left, top, width, height = geometry
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Emu(left),
        Emu(top),
        Emu(width),
        Emu(height),
    )
    shape.fill.background()
    shape.line.color.rgb = rgb(theme.colors.border)
    shape.line.width = Emu(theme.spacing.divider_emu)
    shape.shadow.inherit = False
    set_chrome_shape(shape, f"diagram-frame:{namespace}")
    return shape


__all__ = ["CACHE_DIR", "render_diagram_block"]

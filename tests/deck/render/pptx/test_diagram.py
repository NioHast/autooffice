"""Tes integrasi block diagram PlantUML sebagai picture native PPTX."""

import base64
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

import autooffice.deck.render.pptx.diagram as diagram_module
from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.media.plantuml import PLANTUML_ENV_VAR, PlantUmlError
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyKind,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.coverage import CoverageError
from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.protocol import OutputTarget, RenderRequest, RenderResult
from autooffice.design.theme import Theme

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _fake_plantuml(
    monkeypatch: pytest.MonkeyPatch,
    *,
    render_error: PlantUmlError | None = None,
    resolve_error: PlantUmlError | None = None,
) -> list[tuple[Path, Path, Theme]]:
    """Ganti pemanggilan PlantUML dengan implementasi deterministik."""
    calls: list[tuple[Path, Path, Theme]] = []

    def fake_resolve(deck_root: Path, relative_path: str) -> Path:
        if resolve_error is not None:
            raise resolve_error
        source = deck_root / relative_path
        assert source.is_file()
        return source

    def fake_render(source: Path, output: Path, *, theme: Theme, cache_dir: Path) -> Path:
        calls.append((source, output, theme))
        assert cache_dir == output.parent
        assert output.suffix == ".png"
        if render_error is not None:
            raise render_error
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(PNG_1X1)
        return output

    monkeypatch.setattr(diagram_module, "resolve_plantuml_source", fake_resolve)
    monkeypatch.setattr(diagram_module, "render_plantuml", fake_render)
    return calls


def _binding(
    key: str,
    *,
    block_id: str,
    leaf: str,
    kind: KeyKind = "text",
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id="s01",
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, leaf),
        value="nilai",
        plain_text="nilai",
    )


def _diagram_case(
    *,
    alt: str = "Diagram alur build",
    caption: str = "Alur build",
    source: str = "diagrams/flow.puml",
    with_caption_key: bool = True,
) -> tuple[DeckIR, LayoutPlan]:
    fields: dict[str, object] = {
        "source": source,
        "alt": alt,
    }
    if caption:
        fields["caption"] = caption
    block = BlockIR("process", "diagram", None, None, fields)
    bindings: list[KeyBinding] = []
    if caption and with_caption_key:
        bindings.append(
            _binding(
                "s01.process.caption",
                block_id="process",
                leaf="caption",
                kind="media_text",
            )
        )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Diagram Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "diagram", 0, (block,), None, None),),
        keys=KeyManifest(tuple(bindings)),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (PlacedBlock("process", 914400, 609600, 8000000, 4000000),),
                (),
            ),
        )
    )
    return deck, layout


def _render(
    deck: DeckIR,
    layout: LayoutPlan,
    workspace: Path,
    theme: Theme,
) -> RenderResult:
    return PptxRenderer().render(
        RenderRequest(
            deck=deck,
            layout=layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=workspace,
        )
    )


def _write_diagram(workspace: Path) -> Path:
    source = workspace / "diagrams" / "flow.puml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "@startuml\nstart\n:Mulai;\n:Selesai;\nstop\n@enduml\n",
        encoding="utf-8",
    )
    return source


def test_diagram_block_inserts_picture_caption_and_coverage(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_plantuml(monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case()

    result = _render(deck, layout, workspace, theme)
    presentation = Presentation(str(result.artifact_path))
    shapes = {shape.name: shape for shape in presentation.slides[0].shapes}

    picture = shapes["autooffice:diagram:s01.process"]
    assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE
    node = picture._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("title") == "s01.process"
    assert node.get("descr") == "Diagram alur build"
    caption = shapes["autooffice:key:s01.process.caption"]
    assert caption.text_frame.text == "Alur build"
    assert result.coverage.ok is True
    assert result.coverage.missing_alt == ()
    cache_dir = workspace / "cache" / "plantuml"
    assert len(list(cache_dir.glob("*.png"))) == 1
    assert (cache_dir / "s01.process.png").is_file()
    assert sorted(path.name for path in (workspace / "cache").iterdir()) == ["plantuml"]


def test_diagram_without_caption_has_only_picture(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_plantuml(monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case(caption="")

    result = _render(deck, layout, workspace, theme)
    presentation = Presentation(str(result.artifact_path))
    shapes = list(presentation.slides[0].shapes)

    assert len(shapes) == 1
    assert shapes[0].name == "autooffice:diagram:s01.process"
    assert shapes[0].shape_type == MSO_SHAPE_TYPE.PICTURE
    assert result.coverage.ok is True
    assert (workspace / "cache" / "plantuml" / "s01.process.png").is_file()


def test_diagram_missing_plantuml_fails_without_pptx_fallback(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = PlantUmlError(
        "PlantUML tidak ditemukan di PATH. Pasang PlantUML sebelum build diagram.",
        code="PLANTUML-TOOL",
    )
    _fake_plantuml(monkeypatch, render_error=error)
    _write_diagram(workspace)
    deck, layout = _diagram_case()

    with pytest.raises(
        PptxRenderError,
        match=r"diagram PlantUML.*PlantUML tidak ditemukan",
    ):
        _render(deck, layout, workspace, theme)

    assert not (workspace / "diagram-deck.pptx").exists()
    assert list(workspace.glob("*.pptx")) == []
    assert list((workspace / "cache" / "plantuml").glob("*.png")) == []


def test_diagram_missing_alt_fails_coverage(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_plantuml(monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case(alt="")

    with pytest.raises(CoverageError) as error:
        _render(deck, layout, workspace, theme)

    assert error.value.report.missing_alt == ("s01.process",)
    assert not (workspace / "diagram-deck.pptx").exists()


def test_diagram_missing_caption_key_fails_coverage(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_plantuml(monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case(with_caption_key=False)

    with pytest.raises(CoverageError) as error:
        _render(deck, layout, workspace, theme)

    assert error.value.report.unkeyed_visible == ("s01.process.caption",)
    assert not (workspace / "diagram-deck.pptx").exists()


def test_diagram_source_traversal_fails_before_render(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_plantuml(
        monkeypatch,
        resolve_error=PlantUmlError(
            "Path diagram tidak boleh memuat '..': '../flow.puml'.",
            code="PLANTUML-SOURCE",
        ),
    )
    deck, layout = _diagram_case(source="../flow.puml")

    with pytest.raises(PptxRenderError, match=r"diagram PlantUML.*\.\."):
        _render(deck, layout, workspace, theme)

    assert not (workspace / "diagram-deck.pptx").exists()


def test_minimal_deck_does_not_need_plantuml(
    minimal_case,
    theme: Theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_plantuml(monkeypatch)
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "tidak-ada-plantuml"))

    result = PptxRenderer().render(
        RenderRequest(
            deck=minimal_case.deck,
            layout=minimal_case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=minimal_case.workspace,
        )
    )

    assert calls == []
    assert result.artifact_path.is_file()
    assert result.coverage.ok is True

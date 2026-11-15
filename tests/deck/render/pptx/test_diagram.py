"""Tes integrasi block diagram PlantUML sebagai picture native PPTX."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

import autooffice.deck.media.plantuml as plantuml_module
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

FAKE_PLANTUML_VERSION = ".".join(str(part) for part in plantuml_module.MIN_PLANTUML_VERSION)

FAKE_PLANTUML = f"""\
import base64
import json
import os
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
log_path = os.environ.get("FAKE_PLANTUML_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments) + "\\n")

if arguments == ["--version"]:
    print("PlantUML version {FAKE_PLANTUML_VERSION} (fake)")
    raise SystemExit(0)

source = sys.stdin.buffer.read()
if not source:
    print("fake plantuml: stdin kosong", file=sys.stderr)
    raise SystemExit(2)
if "--png" not in arguments or "-pipe" not in arguments:
    print("fake plantuml: butuh --png dan -pipe", file=sys.stderr)
    raise SystemExit(2)

sys.stdout.buffer.write(PNG)
sys.stdout.buffer.flush()
"""


def _install_fake_plantuml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pasang executable PlantUML palsu lewat override environment."""
    script = tmp_path / "fake-plantuml.py"
    script.write_text(FAKE_PLANTUML, encoding="utf-8", newline="\n")
    log = tmp_path / "plantuml-calls.jsonl"
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(script))
    monkeypatch.setenv("FAKE_PLANTUML_LOG", str(log))
    monkeypatch.setattr(plantuml_module, "_VERSION_CACHE", {})
    return log


def _fake_plantuml(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path, Theme]]:
    """Ganti pemanggilan PlantUML dengan implementasi deterministik."""
    calls: list[tuple[Path, Path, Theme]] = []

    def fake_resolve(deck_root: Path, relative_path: str) -> Path:
        source = deck_root / relative_path
        assert source.is_file()
        return source

    def fake_render(source: Path, output: Path, *, theme: Theme, cache_dir: Path) -> Path:
        calls.append((source, output, theme))
        assert cache_dir == output.parent
        assert output.suffix == ".png"
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


def test_diagram_renders_real_plantuml_into_cache(
    workspace: Path,
    theme: Theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls_log = _install_fake_plantuml(tmp_path, monkeypatch)
    source = _write_diagram(workspace)
    deck, layout = _diagram_case()

    result = _render(deck, layout, workspace, theme)

    presentation = Presentation(str(result.artifact_path))
    shapes = {shape.name: shape for shape in presentation.slides[0].shapes}
    picture = shapes["autooffice:diagram:s01.process"]
    assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE
    node = picture._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("descr") == "Diagram alur build"
    assert result.coverage.ok is True

    cache_dir = workspace / "cache" / "plantuml"
    cached = list(cache_dir.glob("plantuml-*.png"))
    assert len(cached) == 1
    assert (cache_dir / "s01.process.png").is_file()
    metadata = json.loads(cached[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert metadata["theme"]["name"] == theme.name
    assert metadata["plantuml_version"] == FAKE_PLANTUML_VERSION

    calls = [
        json.loads(line) for line in calls_log.read_text(encoding="utf-8").splitlines() if line
    ]
    assert ["--version"] in calls
    render_call = next(call for call in calls if "--version" not in call)
    assert "-secure" in render_call


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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PLANTUML_ENV_VAR, str(tmp_path / "tidak-ada-plantuml"))
    _write_diagram(workspace)
    deck, layout = _diagram_case()

    with pytest.raises(PptxRenderError, match=r"PlantUML tidak ditemukan") as error:
        _render(deck, layout, workspace, theme)

    cause = error.value.__cause__
    assert isinstance(cause, PlantUmlError)
    assert cause.code == "PLANTUML-TOOL"
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


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("diagrams/missing.puml", r"Diagram PlantUML tidak ditemukan"),
        ("../flow.puml", r"tidak boleh memuat segmen kosong"),
    ],
    ids=["missing", "traversal"],
)
def test_diagram_invalid_source_fails_before_render(
    workspace: Path,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    message: str,
) -> None:
    def unexpected_render(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("render tidak boleh dipanggil saat sumber invalid")

    monkeypatch.setattr(diagram_module, "render_plantuml", unexpected_render)
    deck, layout = _diagram_case(source=source)

    with pytest.raises(PptxRenderError, match=message) as error:
        _render(deck, layout, workspace, theme)

    cause = error.value.__cause__
    assert isinstance(cause, PlantUmlError)
    assert cause.code == "PLANTUML-SOURCE"
    assert not (workspace / "diagram-deck.pptx").exists()


def test_minimal_deck_does_not_need_plantuml(
    minimal_case,
    theme: Theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_find() -> Path | None:
        raise AssertionError("deck tanpa diagram tidak boleh mencari PlantUML")

    monkeypatch.setattr(plantuml_module, "find_plantuml", unexpected_find)

    result = PptxRenderer().render(
        RenderRequest(
            deck=minimal_case.deck,
            layout=minimal_case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=minimal_case.workspace,
        )
    )

    assert result.artifact_path.is_file()
    assert result.coverage.ok is True

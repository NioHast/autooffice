"""Tes kontrak doctor: aset font terbundel, bukan font terpasang."""

from pathlib import Path

import pytest

from autooffice.cli import doctor
from autooffice.design import fonts


def _patch_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tools: dict[str, str] | None = None,
    font_assets_status: tuple[bool, str] = (True, "aset font siap"),
) -> None:
    """Isolasi laporan doctor dari Pandoc dan PlantUML yang terpasang."""
    available = tools or {}
    plantuml = Path(available["plantuml"]) if "plantuml" in available else None

    monkeypatch.setattr(doctor, "_find_tool", lambda name: available.get(name))
    monkeypatch.setattr(
        doctor,
        "_tool_version",
        lambda command: f"{command} 1.0" if command else None,
    )
    monkeypatch.setattr(doctor, "_find_plantuml", lambda: plantuml)
    monkeypatch.setattr(
        doctor,
        "_plantuml_release",
        lambda found: "1.2026.10" if found is not None else None,
    )
    monkeypatch.setattr(doctor, "_font_assets_status", lambda: font_assets_status)
    monkeypatch.setattr(doctor, "_google_status", lambda: (True, "google siap"))
    monkeypatch.setattr(doctor.os, "access", lambda *_args: True)


@pytest.mark.parametrize(
    ("targets", "required"),
    [
        (None, {"python", "workspace", "pandoc", "font-assets"}),
        (("pptx",), {"python", "workspace", "font-assets"}),
    ],
)
def test_doctor_does_not_require_installed_fonts(
    monkeypatch: pytest.MonkeyPatch,
    targets: tuple[str, ...] | None,
    required: set[str],
) -> None:
    _patch_report(monkeypatch, tools={"pandoc": "pandoc"})

    report = doctor.doctor_report(targets)

    names = {check.name for check in report.checks}
    assert "fonts" not in names
    assert {check.name for check in report.checks if check.required} == required
    assert {check.name: check.ok for check in report.checks} == {
        "python": True,
        "pandoc": True,
        "plantuml": False,
        "font-assets": True,
        "google": True,
        "workspace": True,
    }
    assert report.ok is True


@pytest.mark.parametrize("targets", [None, ("pptx",), ("slides",)])
def test_doctor_requires_bundled_font_assets(
    monkeypatch: pytest.MonkeyPatch,
    targets: tuple[str, ...] | None,
) -> None:
    _patch_report(
        monkeypatch,
        tools={"pandoc": "pandoc"},
        font_assets_status=(False, "aset font hilang: LiberationSans-Regular.ttf"),
    )

    report = doctor.doctor_report(targets)

    check = next(item for item in report.checks if item.name == "font-assets")
    assert check.required is True
    assert check.ok is False
    assert report.ok is False


def test_font_assets_failure_has_no_remediation_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"hilang.ttf": "hash"})

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert detail == "aset font hilang: hilang.ttf"
    assert "python tools" not in detail

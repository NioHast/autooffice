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
    available = tools or {}

    monkeypatch.setattr(doctor, "_find_tool", lambda name: available.get(name))
    monkeypatch.setattr(
        doctor,
        "_tool_version",
        lambda command: f"{command} 1.0" if command else None,
    )
    monkeypatch.setattr(doctor, "_font_assets_status", lambda: font_assets_status)
    monkeypatch.setattr(doctor, "_google_status", lambda: (True, "google siap"))
    monkeypatch.setattr(doctor.os, "access", lambda *_args: True)


@pytest.mark.parametrize("targets", [None, ("pptx",)])
def test_doctor_does_not_require_installed_fonts(
    monkeypatch: pytest.MonkeyPatch,
    targets: tuple[str, ...] | None,
) -> None:
    _patch_report(monkeypatch, tools={"pandoc": "pandoc"})

    report = doctor.doctor_report(targets)

    names = {check.name for check in report.checks}
    assert "fonts" not in names
    assert "font-assets" in names
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

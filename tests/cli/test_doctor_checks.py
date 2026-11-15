"""Tes doctor tanpa jaringan: tool, font, target, dan format laporan."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import autooffice.deck.media.plantuml as plantuml_module
import autooffice.google
from autooffice.cli import doctor
from autooffice.deck.media.plantuml import PlantUmlError
from autooffice.design import fonts


def _patch_offline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tools: dict[str, str] | None = None,
    plantuml_release: str | None = "1.2026.10",
    plantuml_error: PlantUmlError | None = None,
    font_assets_status: tuple[bool, str] = (True, "aset font siap"),
    google_status: tuple[bool, str] | None = (True, "google siap"),
) -> None:
    available = tools or {}
    executable = available.get("plantuml")

    def fake_find_plantuml() -> Path | None:
        return Path(executable) if executable else None

    def fake_plantuml_version(_executable: Path) -> str:
        if plantuml_error is not None:
            raise plantuml_error
        assert plantuml_release is not None
        return plantuml_release

    monkeypatch.setattr(doctor, "_find_tool", lambda name: available.get(name))
    monkeypatch.setattr(
        doctor,
        "_tool_version",
        lambda command: f"{command} 1.0" if command else None,
    )
    monkeypatch.setattr(plantuml_module, "find_plantuml", fake_find_plantuml)
    monkeypatch.setattr(plantuml_module, "plantuml_version", fake_plantuml_version)
    if hasattr(doctor, "find_plantuml"):
        monkeypatch.setattr(doctor, "find_plantuml", fake_find_plantuml)
    if hasattr(doctor, "plantuml_version"):
        monkeypatch.setattr(doctor, "plantuml_version", fake_plantuml_version)
    monkeypatch.setattr(doctor, "_font_assets_status", lambda: font_assets_status)
    if google_status is not None:
        monkeypatch.setattr(doctor, "_google_status", lambda: google_status)
    monkeypatch.setattr(doctor.os, "access", lambda *_args: True)


@pytest.mark.parametrize(
    ("targets", "required"),
    [
        (None, {"python", "workspace", "pandoc", "font-assets"}),
        (("docx",), {"python", "workspace", "pandoc"}),
        (("pptx",), {"python", "workspace", "font-assets"}),
        (("slides",), {"python", "workspace", "font-assets", "google"}),
        (
            ("docx", "pptx", "slides"),
            {
                "python",
                "workspace",
                "pandoc",
                "font-assets",
                "google",
            },
        ),
    ],
)
def test_doctor_required_checks_follow_targets(
    monkeypatch: pytest.MonkeyPatch,
    targets: tuple[str, ...] | None,
    required: set[str],
) -> None:
    _patch_offline(monkeypatch, tools={"pandoc": "pandoc", "plantuml": "/opt/plantuml"})

    report = doctor.doctor_report(targets)

    assert {check.name for check in report.checks if check.required} == required
    assert report.ok is True
    assert report.targets == targets
    assert {"word", "powerpoint", "pywin32"} & {check.name for check in report.checks} == set()


def test_doctor_plantuml_check_reports_version_and_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "plantuml.jar"
    _patch_offline(monkeypatch, tools={"plantuml": str(executable)})

    report = doctor.doctor_report(("pptx",))

    check = next(check for check in report.checks if check.name == "plantuml")
    assert check.ok is True
    assert check.required is False
    assert check.detail == f"1.2026.10 - {executable}"
    assert report.ok is True


def test_doctor_missing_plantuml_is_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(monkeypatch, tools={"pandoc": "pandoc"})

    report = doctor.doctor_report(None)

    check = next(check for check in report.checks if check.name == "plantuml")
    assert check.ok is False
    assert check.required is False
    assert check.detail == "tidak ditemukan; diperlukan hanya untuk diagram PlantUML"
    assert report.ok is True


def test_doctor_plantuml_version_failure_reports_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "plantuml.jar"
    _patch_offline(
        monkeypatch,
        tools={"plantuml": str(executable)},
        plantuml_error=PlantUmlError("versi tidak terbaca"),
    )

    report = doctor.doctor_report(("pptx",))

    check = next(check for check in report.checks if check.name == "plantuml")
    assert check.ok is True
    assert check.required is False
    assert check.detail == str(executable)
    assert report.ok is True


def test_doctor_slides_requires_font_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        font_assets_status=(True, "aset font siap"),
    )

    report = doctor.doctor_report(("slides",))

    assert report.ok is True
    assert next(check for check in report.checks if check.name == "font-assets").required is True
    assert "fonts" not in {check.name for check in report.checks}


def test_doctor_slides_fails_without_google_oauth_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        google_status=(False, "kredensial Google belum siap: token hilang"),
    )

    report = doctor.doctor_report(("slides",))

    assert report.ok is False
    google = next(check for check in report.checks if check.name == "google")
    assert google.required is True
    assert google.ok is False
    assert "token" in google.detail


def test_doctor_report_fails_on_missing_required_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(monkeypatch, tools={})

    report = doctor.doctor_report(None)

    assert report.ok is False
    pandoc = next(check for check in report.checks if check.name == "pandoc")
    assert pandoc.ok is False
    assert pandoc.required is True
    assert "tidak ditemukan" in pandoc.detail


def test_render_doctor_human_output_success(capsys: pytest.CaptureFixture[str]) -> None:
    report = doctor.DoctorReport(
        checks=(doctor.DoctorCheck("python", True, True, "3.15.2"),),
        targets=None,
        ok=True,
    )

    assert doctor.render_doctor(report, json_output=False) == 0
    output = capsys.readouterr().out
    assert "[OK] python" in output
    assert "wajib" in output
    assert "Kesimpulan: dependency wajib untuk target yang diminta tersedia." in output


def test_render_doctor_human_output_failure(capsys: pytest.CaptureFixture[str]) -> None:
    report = doctor.DoctorReport(
        checks=(doctor.DoctorCheck("pandoc", False, True, "tidak ditemukan"),),
        targets=None,
        ok=False,
    )

    assert doctor.render_doctor(report, json_output=False) == 1
    output = capsys.readouterr().out
    assert "[--] pandoc" in output
    assert "wajib" in output
    assert "dependency wajib belum lengkap" in output


def test_find_tool_non_windows_uses_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert doctor._find_tool("pandoc") == "/usr/bin/pandoc"


def test_find_tool_windows_prefers_localappdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "local" / "Pandoc" / "pandoc.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))

    assert doctor._find_tool("pandoc") == str(executable)


def test_find_tool_windows_prefers_program_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "program" / "Pandoc" / "pandoc.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))

    assert doctor._find_tool("pandoc") == str(executable)


def test_find_tool_windows_falls_back_to_which(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))
    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: "C:/tools/pandoc.exe" if name == "pandoc.exe" else None,
    )

    assert doctor._find_tool("pandoc") == "C:/tools/pandoc.exe"


def test_find_tool_windows_without_env_paths_uses_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "pandoc" if name == "pandoc" else None)

    assert doctor._find_tool("pandoc") == "pandoc"


def test_find_tool_windows_non_pandoc_uses_which(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))
    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: "plantuml" if name == "plantuml" else None,
    )

    assert doctor._find_tool("plantuml") == "plantuml"


def test_tool_version_none_command_returns_none() -> None:
    assert doctor._tool_version(None) is None


def test_tool_version_handles_subprocess_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("executable hilang")

    monkeypatch.setattr(doctor.subprocess, "run", fail)

    assert doctor._tool_version("pandoc") is None


def test_font_assets_status_reports_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"hilang.ttf": "hash"})

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert "aset font hilang" in detail
    assert "hilang.ttf" in detail


def test_font_assets_status_reports_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "rusak.ttf").write_bytes(b"font")
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"rusak.ttf": "hash"})

    def fail_sha(_path: Path) -> str:
        raise OSError("tidak dapat dibaca")

    monkeypatch.setattr(fonts, "sha256", fail_sha)

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert "aset font hilang" in detail


def test_font_assets_status_reports_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "beda.ttf").write_bytes(b"font")
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"beda.ttf": "hash-asli"})
    monkeypatch.setattr(fonts, "sha256", lambda _path: "hash-lain")

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert "hash font tidak cocok" in detail
    assert "beda.ttf" in detail


def test_font_assets_status_accepts_matching_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "baik.ttf").write_bytes(b"font")
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"baik.ttf": "hash"})
    monkeypatch.setattr(fonts, "FONT_FILES", ("baik.ttf",))
    monkeypatch.setattr(fonts, "sha256", lambda _path: "hash")

    ok, detail = doctor._font_assets_status()

    assert ok is True
    assert "1 TTF + lisensi" in detail
    assert str(tmp_path) in detail


@pytest.mark.parametrize("error_type", [ModuleNotFoundError, ValueError])
def test_google_status_handles_unavailable_parent_spec(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    def fail_find_spec(_name: str) -> None:
        raise error_type("google tidak tersedia")

    monkeypatch.setattr(doctor.importlib.util, "find_spec", fail_find_spec)

    assert doctor._google_status() == (False, "google extra tidak terpasang")


def test_google_status_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name) if name == "google" else None,
    )

    ok, detail = doctor._google_status()

    assert ok is False
    assert "googleapiclient" in detail


def test_doctor_report_survives_google_auth_find_spec_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        tools={"pandoc": "pandoc"},
        google_status=None,
    )

    def fail_google_auth(name: str) -> SimpleNamespace:
        if name == "google.auth":
            raise ModuleNotFoundError("No module named 'google'")
        return SimpleNamespace(name=name)

    monkeypatch.setattr(doctor.importlib.util, "find_spec", fail_google_auth)

    report = doctor.doctor_report(("docx",))

    google = next(check for check in report.checks if check.name == "google")
    names = {check.name for check in report.checks}
    assert google.ok is False
    assert "google.auth" in google.detail
    assert {"pandoc", "plantuml", "font-assets"} <= names
    assert "fonts" not in names
    assert {"word", "powerpoint", "pywin32"} & names == set()
    assert report.ok is True


def test_google_status_accepts_installed_extra_and_local_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autooffice.google

    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            return cls()

    class _Tokens:
        @classmethod
        def from_environment(cls) -> _Tokens:
            return cls()

        def require(self) -> dict[str, object]:
            return {"access_token": "token"}

    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )
    monkeypatch.setattr(autooffice.google, "OAuthSettings", _Settings, raising=False)
    monkeypatch.setattr(autooffice.google, "TokenStore", _Tokens, raising=False)

    ok, detail = doctor._google_status()

    assert ok is True
    assert "tanpa jaringan" in detail


def test_google_status_reports_missing_oauth_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autooffice.google

    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            raise autooffice.google.GoogleAuthError("GOOGLE_CLIENT_ID kosong")

    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )
    monkeypatch.setattr(autooffice.google, "OAuthSettings", _Settings, raising=False)

    ok, detail = doctor._google_status()

    assert ok is False
    assert "kredensial Google" in detail
    assert "GOOGLE_CLIENT_ID" in detail


@pytest.mark.parametrize(
    ("error_type", "message"),
    [
        (autooffice.google.GoogleAuthError, "token hilang"),
        (OSError, "token tidak dapat dibaca"),
    ],
    ids=["google-auth-error", "os-error"],
)
def test_google_status_reports_token_store_failure(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    message: str,
) -> None:
    calls: list[str] = []

    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            return cls()

    class _Tokens:
        @classmethod
        def from_environment(cls) -> _Tokens:
            calls.append("from_environment")
            return cls()

        def require(self) -> dict[str, object]:
            calls.append("require")
            raise error_type(message)

    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )
    monkeypatch.setattr(autooffice.google, "OAuthSettings", _Settings, raising=False)
    monkeypatch.setattr(autooffice.google, "TokenStore", _Tokens, raising=False)

    ok, detail = doctor._google_status()

    assert ok is False
    assert "kredensial Google" in detail
    assert message in detail
    assert calls == ["from_environment", "require"]

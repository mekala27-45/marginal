"""The claim gate renders documents from the manifest and diffs whole files."""

from __future__ import annotations

from pathlib import Path

import pytest
from marginal_core.manifest import Manifest
from marginal_render.render import ClaimGateError, Renderer, Target, hand_typed_numbers
from marginal_render.targets import discover


def _setup(tmp_path: Path) -> tuple[Renderer, Path]:
    templates = tmp_path / "docs" / "templates"
    templates.mkdir(parents=True)
    (templates / "RESULTS.md.j2").write_text(
        "# Results\n\nThe return on paid search was {{ v('mmm.own.roas.paid_search') }}.\n\n"
        "{{ table('mmm.cross_check') }}\n\n{{ statement() }}\n"
    )
    manifest = Manifest(as_of="2026-09-27", seed=1)
    manifest.put(
        "mmm.own.roas.paid_search", 2.4137, "float2", source="simulated", model="own", population="p", origin="o"
    )
    manifest.put_table(
        "mmm.cross_check",
        ["Channel", "own", "Truth"],
        ["text", "float2", "float2"],
        [["Paid search", 2.41, 2.5]],
        source="simulated",
        model="both",
        population="p",
        origin="o",
    )
    renderer = Renderer(tmp_path, manifest, discover(tmp_path), [templates])
    return renderer, tmp_path / "RESULTS.md"


def test_clean_render_passes(tmp_path: Path) -> None:
    renderer, out = _setup(tmp_path)
    renderer.write_all()
    assert "2.41" in out.read_text()
    assert "Alderquist is a fictional" in out.read_text()
    assert renderer.check_all() == []


def test_a_number_edited_by_hand_is_caught(tmp_path: Path) -> None:
    renderer, out = _setup(tmp_path)
    renderer.write_all()
    out.write_text(out.read_text().replace("was 2.41.", "was 2.60."))
    drifts = renderer.check_all()
    assert len(drifts) == 1
    assert "-The return on paid search was 2.60." in drifts[0].diff
    assert "+The return on paid search was 2.41." in drifts[0].diff


def test_a_missing_document_is_caught(tmp_path: Path) -> None:
    renderer, _ = _setup(tmp_path)
    assert renderer.check_all()[0].output == "RESULTS.md"


def test_refuses_with_no_documents(tmp_path: Path) -> None:
    manifest = Manifest(as_of="2026-09-27", seed=1)
    manifest.put("a.b", 1, "int", source="static", population="p", origin="o")
    with pytest.raises(ClaimGateError, match="no documents"):
        Renderer(tmp_path, manifest, [], [tmp_path])


def test_refuses_with_an_empty_manifest(tmp_path: Path) -> None:
    with pytest.raises(ClaimGateError, match="empty manifest"):
        Renderer(tmp_path, Manifest(as_of="2026-09-27", seed=1), [Target("a.j2", "a.md")], [tmp_path])


def test_unknown_key_fails_loudly(tmp_path: Path) -> None:
    renderer, _ = _setup(tmp_path)
    (tmp_path / "docs" / "templates" / "RESULTS.md.j2").write_text("{{ v('mmm.nothing') }}")
    with pytest.raises(KeyError):
        renderer.write_all()


def test_hand_typed_numbers_are_found_outside_expressions() -> None:
    text = "Return was {{ v('mmm.roas') }} and the share was 0.81 under CC BY 4.0."
    assert hand_typed_numbers(text, ["CC BY 4.0"]) == ["0.81"]
    assert hand_typed_numbers("{{ v('a.b') }} only", []) == []


def test_partials_are_not_rendered_on_their_own(tmp_path: Path) -> None:
    templates = tmp_path / "report" / "templates" / "cards"
    templates.mkdir(parents=True)
    (templates / "_card.md.j2").write_text("x")
    (templates / "mmm_own.md.j2").write_text("{% include 'cards/_card.md.j2' %}")
    targets = discover(tmp_path)
    assert [t.output for t in targets] == ["report/cards/mmm_own.md"]


def test_table_html_right_aligns_numbers(tmp_path: Path) -> None:
    from marginal_render.render import table_html

    renderer, _ = _setup(tmp_path)
    html = table_html(renderer.manifest, "mmm.cross_check")
    assert '<td class="num">2.41</td>' in html
    assert '<th class="txt">Channel</th>' in html

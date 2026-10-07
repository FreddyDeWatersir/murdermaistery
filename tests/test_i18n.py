"""The page in French and Italian (D-209)."""

import re
import shutil
import subprocess

import pytest

from mystery.i18n import LITERALS, SNIPPETS, translate_page
from mystery.jsscan import string_literals
from mystery.web import PAGE

SCRIPT = re.search(r"<script>(.*?)</script>", PAGE, re.S).group(1)
PRESENT = {content for _, _, quote, content in string_literals(SCRIPT) if quote != "`"}


@pytest.mark.parametrize("lang", sorted(LITERALS))
def test_every_entry_still_exists_in_the_page(lang) -> None:
    """A change to the page that renames a sentence fails here, not silently
    in front of a French player."""
    assert [k for k in LITERALS[lang] if k not in PRESENT] == []
    assert [e for e, _ in SNIPPETS[lang] if e not in PAGE] == []


@pytest.mark.parametrize("lang", sorted(LITERALS))
def test_the_translated_page_has_no_english_left_from_the_table(lang) -> None:
    page = translate_page(PAGE, lang)
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    left = {c for _, _, q, c in string_literals(script) if q != "`"} & set(LITERALS[lang])
    assert left == set()
    assert f'<html lang="{lang}">' in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("lang", sorted(LITERALS))
def test_the_translated_script_still_parses(lang, tmp_path) -> None:
    page = translate_page(PAGE, lang)
    script = tmp_path / "page.js"
    script.write_text("\n".join(re.findall(r"<script>(.*?)</script>", page, re.S)), "utf-8")
    assert subprocess.run(["node", "--check", str(script)], capture_output=True).returncode == 0


def test_english_is_untouched() -> None:
    assert translate_page(PAGE, "en") == PAGE


def test_the_scanner_finds_strings_and_skips_comments_and_regexes() -> None:
    src = "/* 'no' */ const a='yes'; // 'no'\nconst r=/'no'/g; const t=`x${f('in')}y`;"
    found = [c for _, _, q, c in string_literals(src) if q != "`"]
    assert found == ["yes", "in"]


def test_a_room_in_italian_is_served_the_italian_page() -> None:
    from fastapi.testclient import TestClient

    from mystery.example import OPENING_NIGHT
    from mystery.models import Mystery
    from mystery.solver import solve
    from mystery.web import Case, build_app

    m = solve(Mystery.model_validate(OPENING_NIGHT)).model_copy(update={"language": "it"})
    client = TestClient(build_app(Case(m, id="it"), lambda s, q: {}, together=True))
    assert "Apri il caso" in client.get("/").text
    state = client.get("/state").json()
    assert state["lang"] == "it" and state["authority"] == "gli agenti"

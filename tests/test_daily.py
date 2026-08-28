"""Tests for the rota: which case is today's, and what happens when there is none.

The scenario worth protecting is the one nobody is awake for. Generation fails
at three in the morning, and the question is whether that costs a shorter queue
or a missing game (D-078).
"""

from mystery.daily import FileRota, shortfall, todays_case, waiting
from mystery.example import OPENING_NIGHT
from mystery.library import save
from mystery.models import Mystery

CASE = Mystery.model_validate(OPENING_NIGHT)


def _shelf(tmp_path, how_many: int):
    folder = tmp_path / "cases"
    made = [save(CASE, "a theatre", "the_lie", n, folder=folder) for n in range(how_many)]
    return folder, tmp_path / "rota.json", [c.id for c in made]


def test_the_first_case_of_the_day_comes_off_the_front_of_the_queue(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 3)

    chosen = todays_case("2026-09-01", folder, rota)

    assert chosen.id == made[0], "oldest first, so nothing goes stale at the bottom"


def test_asking_twice_in_one_day_is_the_same_case(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 3)

    first = todays_case("2026-09-01", folder, rota)
    second = todays_case("2026-09-01", folder, rota)

    assert first.id == second.id


def test_a_new_day_is_a_new_case(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 3)

    monday = todays_case("2026-09-01", folder, rota)
    tuesday = todays_case("2026-09-02", folder, rota)

    assert monday.id != tuesday.id
    assert len(waiting(folder, rota)) == 1


def test_an_empty_buffer_says_so_rather_than_generating(tmp_path) -> None:
    """The honest failure, and the one that gets noticed."""
    folder, rota, made = _shelf(tmp_path, 1)
    todays_case("2026-09-01", folder, rota)

    assert todays_case("2026-09-02", folder, rota) is None


def test_a_night_the_job_failed_costs_a_shorter_queue_and_nothing_else(tmp_path) -> None:
    """The whole reason the buffer exists. Four days of cases are waiting; the
    generator fails every night for three nights; players notice nothing."""
    folder, rota, made = _shelf(tmp_path, 4)

    for day in ("2026-09-01", "2026-09-02", "2026-09-03"):
        assert todays_case(day, folder, rota) is not None

    assert len(waiting(folder, rota)) == 1


def test_the_job_knows_how_many_to_make(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 2)

    assert shortfall(folder, rota, want=4) == 2

    todays_case("2026-09-01", folder, rota)
    assert shortfall(folder, rota, want=4) == 3, "a served case no longer counts as waiting"


def test_a_full_buffer_asks_for_nothing(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 5)

    assert shortfall(folder, rota, want=4) == 0


def test_a_corrupt_rota_does_not_take_the_game_down(tmp_path) -> None:
    """Worst case is a case served twice, which nobody will die of."""
    folder, rota, made = _shelf(tmp_path, 2)
    rota.write_text("{ not json", encoding="utf-8")

    assert FileRota(rota).case_for("2026-09-01") is None
    assert todays_case("2026-09-01", folder, rota) is not None


def test_a_case_deleted_off_the_shelf_does_not_strand_the_day(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 2)
    chosen = todays_case("2026-09-01", folder, rota)
    next(folder.glob(f"*__{chosen.id}.json")).unlink()

    assert todays_case("2026-09-01", folder, rota) is not None


def test_the_first_claim_of_a_day_wins_and_the_second_is_told_so(tmp_path) -> None:
    """The line that makes two servers agree without either knowing the other
    exists. Whoever gets there first decides; everybody else is told."""
    folder, rota, made = _shelf(tmp_path, 2)
    book = FileRota(rota)

    first = book.claim("2026-09-01", made[0])
    second = book.claim("2026-09-01", made[1])

    assert first == made[0]
    assert second == made[0], "the loser is handed the winner's answer"


def test_two_servers_starting_at_once_serve_one_case(tmp_path) -> None:
    folder, rota, made = _shelf(tmp_path, 3)

    one = todays_case("2026-09-01", folder, FileRota(rota))
    two = todays_case("2026-09-01", folder, FileRota(rota))

    assert one.id == two.id
    assert len(waiting(folder, FileRota(rota))) == 2, "one case used, not two"


def test_releasing_a_day_lets_it_be_claimed_again(tmp_path) -> None:
    """Only the repair path uses this. `claim` will not overwrite, which is the
    point of it, so a day pointing at a deleted case needs a way out."""
    folder, rota, made = _shelf(tmp_path, 2)
    book = FileRota(rota)
    book.claim("2026-09-01", made[0])

    book.release("2026-09-01")

    assert book.case_for("2026-09-01") is None
    assert book.claim("2026-09-01", made[1]) == made[1]

from __future__ import annotations

import pytest

from backend.errors import ValidationFailed
from backend.lyric_quality import (
    _has_consistent_rhyme_scheme,
    _rhyme_key,
    _validate_fatigue_terms,
    validate_lyric_batch,
    validate_title_assignments,
)
from tests.test_ai_lyrics import make_valid_generation_song


def _song_with_style(style: str):
    return make_valid_generation_song("第一首").model_copy(update={"style": style})


@pytest.mark.parametrize(
    "opening",
    [
        "a dry snare hit lands on the very first beat",
        "a door-slam kick hits the first second",
        "a clipped guitar stab opens in the first second",
        "cold-opening on a single clipped guitar note",
        "a fuzz stab hits at the very top",
        "one bent note rings right away",
        "a signature snap opens the track",
    ],
)
def test_style_accepts_varied_first_second_signature_phrasings(opening: str) -> None:
    style = (
        f"indie pop with a warm mood, soft male vocal, clean guitar, brushed drums; {opening}\n"
        "BPM 88 | Key A minor | Vocals: male lead\n"
        "Arrangement: cold open -> intimate verse -> wide chorus"
    )

    validate_lyric_batch([_song_with_style(style)])


def test_style_signature_can_be_declared_outside_first_line() -> None:
    style = (
        "indie pop with a warm mood, soft male vocal, clean guitar, brushed drums\n"
        "BPM 88 | Key A minor | signature motif starts the track\n"
        "Arrangement: cold open -> intimate verse -> wide chorus"
    )

    validate_lyric_batch([_song_with_style(style)])


def test_style_rejects_missing_first_second_signature() -> None:
    style = (
        "indie pop with a warm mood, soft male vocal, clean guitar, brushed drums\n"
        "BPM 88 | Key A minor | Vocals: male lead\n"
        "Arrangement: cold open -> intimate verse -> wide chorus"
    )

    with pytest.raises(ValidationFailed) as error:
        validate_lyric_batch([_song_with_style(style)])

    assert "首秒声音签名" in error.value.message


def test_title_assignments_enforce_per_song_length() -> None:
    songs = [
        make_valid_generation_song("夜色"),
        make_valid_generation_song("晚风里"),
    ]

    validate_title_assignments(
        songs,
        [
            {"required_title_length": 2},
            {"required_title_length": 3},
        ],
    )


def test_title_assignments_reject_wrong_length() -> None:
    songs = [make_valid_generation_song("夜色里")]

    with pytest.raises(ValidationFailed) as error:
        validate_title_assignments(songs, [{"required_title_length": 2}])

    assert "歌名应为 2 字" in error.value.message


def test_title_assignments_reject_length_count_mismatch() -> None:
    songs = [make_valid_generation_song("夜色")]

    with pytest.raises(ValidationFailed):
        validate_title_assignments(
            songs,
            [{"required_title_length": 2}, {"required_title_length": 3}],
        )


@pytest.mark.parametrize(
    "pair",
    [
        ("我一直站在你身后", "从不敲门我把汤放下就走"),  # ou / iou
        ("轮到你疼轮到你等", "轮到你把我受的冷一口吞"),  # eng / uen
        ("天亮我喊你吃饭", "你别怕夜里的光"),  # an / ang
        ("你发的长文我懒得看清", "曾经我求你别再烦人"),  # ing / en
    ],
)
def test_near_rhyme_families_group_expected_endings(pair: tuple[str, str]) -> None:
    first, second = pair

    assert _rhyme_key(first) == _rhyme_key(second)


def test_unrelated_endings_stay_in_separate_families() -> None:
    assert _rhyme_key("我把话咽回") != _rhyme_key("你转身就走")


@pytest.mark.parametrize(
    ("scheme", "expected"),
    [
        (["a", "a", "a", "a"], True),
        (["a", "a", "b", "b"], True),
        (["a", "b", "a", "b"], True),
        (["a", "b", "c", "c"], False),
        (["a", "a", "b"], False),
    ],
)
def test_consistent_rhyme_schemes(scheme: list[str], expected: bool) -> None:
    assert _has_consistent_rhyme_scheme(scheme) is expected


def test_fatigue_term_allows_two_songs_out_of_ten() -> None:
    songs = [make_valid_generation_song(f"测{i}") for i in range(10)]
    songs[0] = songs[0].model_copy(update={"lyrics": songs[0].lyrics + "\n月"})
    songs[7] = songs[7].model_copy(update={"lyrics": songs[7].lyrics + "\n月"})

    _validate_fatigue_terms(songs)


def test_fatigue_term_rejects_three_songs_out_of_ten() -> None:
    songs = [make_valid_generation_song(f"测{i}") for i in range(10)]
    for index in (0, 4, 8):
        songs[index] = songs[index].model_copy(
            update={"lyrics": songs[index].lyrics + "\n月"}
        )

    with pytest.raises(ValidationFailed) as error:
        _validate_fatigue_terms(songs)

    assert "月 3 首" in error.value.message
    assert "最多允许 2 首" in error.value.message

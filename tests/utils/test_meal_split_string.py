from app.utils.meal import split_string


def test_split_string_splits_all_whitespace_when_no_special_delimiter_exists() -> None:
    menu_text = "제육볶음  비빔밥 \n계란후라이\t  어묵국"

    assert split_string(menu_text) == [
        "제육볶음",
        "비빔밥",
        "계란후라이",
        "어묵국",
    ]


def test_split_string_treats_repeated_mixed_whitespace_as_one_separator() -> None:
    menu_text = "김치찌개\t \t  돈까스\n\n   샐러드"

    assert split_string(menu_text) == ["김치찌개", "돈까스", "샐러드"]


def test_split_string_replaces_special_delimiters_with_newlines() -> None:
    menu_text = "돈까스/우동-김치찌개;계란말이|단무지, 콜라"

    assert split_string(menu_text) == [
        "돈까스",
        "우동",
        "김치찌개",
        "계란말이",
        "단무지",
        "콜라",
    ]


def test_split_string_preserves_spaces_inside_newline_chunks_when_special_delimiter_exists() -> None:
    menu_text = "제육볶음  비빔밥 / 계란후라이"

    assert split_string(menu_text) == ["제육볶음  비빔밥", "계란후라이"]

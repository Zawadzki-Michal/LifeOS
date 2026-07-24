from app.routing import strip_local_prefix


def test_strips_local_prefix():
    assert strip_local_prefix("Local: add expense 20 PLN coffee") == (
        True,
        "add expense 20 PLN coffee",
    )


def test_prefix_is_case_insensitive():
    assert strip_local_prefix("LOCAL: hi")[0] is True
    assert strip_local_prefix("local: hi")[0] is True
    assert strip_local_prefix("LoCaL:hi")[0] is True


def test_tolerates_leading_whitespace_and_no_space_after_colon():
    assert strip_local_prefix("   Local:hi") == (True, "hi")


def test_no_prefix_returns_original_text_unchanged():
    assert strip_local_prefix("what should I eat today?") == (
        False,
        "what should I eat today?",
    )


def test_local_elsewhere_in_the_sentence_is_not_a_prefix():
    assert strip_local_prefix("is there a local bakery nearby?") == (
        False,
        "is there a local bakery nearby?",
    )

from tokenbench.core.tokenizer import count_tokens


def test_empty_string_is_zero():
    assert count_tokens("") == 0


def test_known_short_string_is_positive():
    n = count_tokens("hello world")
    assert n > 0
    assert n < 10  # short text, can't be more than a handful of tokens


def test_longer_text_more_tokens():
    short = count_tokens("hello")
    long = count_tokens("hello " * 100)
    assert long > short

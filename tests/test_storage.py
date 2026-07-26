from mcp_server.storage import slugify


def test_slugify_keeps_non_latin_scripts_readable() -> None:
    # Study topics are frequently in Korean; the original implementation
    # ASCII-encoded and dropped anything non-Latin, so every Korean topic
    # fell back to an opaque "topic-<hash>" directory name. Confirm the
    # slug stays human-readable instead.
    assert slugify("베이즈 정리") == "베이즈-정리"
    assert slugify("피보나치 수열") == "피보나치-수열"


def test_slugify_lowercases_and_collapses_latin_punctuation() -> None:
    assert slugify("Quantum Mechanics 101!") == "quantum-mechanics-101"
    assert slugify("  spaces   and---dashes  ") == "spaces-and-dashes"


def test_slugify_falls_back_to_hash_for_punctuation_only_input() -> None:
    slug = slugify("!!!")
    assert slug.startswith("topic-")
    assert slugify("!!!") == slug  # stable across calls

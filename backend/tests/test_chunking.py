from app.services.chunking import chunk_text


def test_chunking_prefers_word_boundaries_and_keeps_overlap():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    chunks = chunk_text(text, chunk_size=18, overlap=5)
    assert len(chunks) > 1
    assert all(not chunk.startswith(" ") and not chunk.endswith(" ") for chunk in chunks)
    assert all("  " not in chunk for chunk in chunks)
    assert "gamma" in " ".join(chunks)


def test_chunking_preserves_a_word_longer_than_target_size():
    chunks = chunk_text("short supercalifragilisticexpialidocious tail", chunk_size=10, overlap=2)
    combined = " ".join(chunks)
    assert all(word in combined for word in ("short", "supercalifragilisticexpialidocious", "tail"))

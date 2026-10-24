def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    text = " ".join(text.split())
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        target_end = min(start + chunk_size, len(text))
        end = target_end
        if target_end < len(text):
            boundary = text.rfind(" ", start + chunk_size // 2, target_end)
            if boundary > start:
                end = boundary
            else:
                next_boundary = text.find(" ", target_end)
                if next_boundary >= 0:
                    end = next_boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        next_start = max(start + 1, end - overlap)
        if overlap:
            boundary = text.find(" ", next_start, min(end + 1, len(text)))
            if boundary >= 0:
                next_start = boundary + 1
        start = next_start

    return chunks

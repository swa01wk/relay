from relay_runtime.speak_text import SpeechTextStream, plain_text_for_speech


def test_plain_text_strips_markdown_bullets():
    raw = "- **Case:** MORT-2931\n- **Rate:** 6.125%"
    spoken = plain_text_for_speech(raw)
    assert "**" not in spoken
    assert "Case:" in spoken
    assert "MORT-2931" in spoken


def test_speech_stream_incremental():
    stream = SpeechTextStream()
    parts = []
    for tok in ["- **", "Case", ":** ", "MORT-2931"]:
        chunk = stream.push(tok)
        if chunk:
            parts.append(chunk)
    parts.append(stream.flush())
    joined = "".join(p for p in parts if p)
    assert "**" not in joined
    assert "MORT-2931" in joined

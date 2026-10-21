"""Chat routing: regex actions on numbered questions, generation requests, greetings, and the LLM fallback."""

from app.services.chat import intent as intent_mod
from app.services.chat.intent import ChatIntent, is_greeting, parse_question_action, route_message
from app.services.generation.runner import format_generation_summary


def test_regenerate_is_not_mistaken_for_new_generation():
    action = parse_question_action("Buat ulang soal nomor 3")
    assert action is not None
    assert action.intent == "regenerate"
    assert action.question_number == 3


def test_level_change_regenerates_with_new_level():
    action = parse_question_action("ubah soal 2 jadi C4")
    assert action is not None
    assert action.intent == "regenerate"
    assert action.bloom_level == "C4-Menganalisis"


def test_feedback_revises_with_instruction():
    action = parse_question_action("Soal no. 1 terlalu mudah")
    assert action is not None
    assert action.intent == "revise"
    assert action.question_number == 1
    assert action.instruction == "Soal no. 1 terlalu mudah"


def test_question_words_route_to_discussion():
    action = parse_question_action("Kenapa jawaban soal nomor 1 begitu?")
    assert action is not None
    assert action.intent == "discuss"
    assert action.question_number == 1


def test_unclear_or_generation_messages_are_not_question_actions():
    assert parse_question_action("soal nomor 1 dong") is None
    assert parse_question_action("Buatkan 3 soal C2 bab 1") is None


def test_greetings():
    assert is_greeting("Halo!")
    assert is_greeting("terima kasih")
    assert not is_greeting("Siapa presiden Amerika?")


def test_route_message_uses_llm_only_for_unclear_messages(monkeypatch):
    calls = []

    def fake_classify(text, history, count):
        calls.append(text)
        return ChatIntent(intent="out_of_scope")

    monkeypatch.setattr(intent_mod, "classify_message", fake_classify)
    assert route_message("Buatkan 5 soal C3", [], 0).intent == "generate"
    assert route_message("ganti soal 2", [], 3).intent == "regenerate"
    assert route_message("halo", [], 0).intent == "help"
    assert calls == []
    assert route_message("Buatkan puisi tentang laut", [], 0).intent == "out_of_scope"
    assert calls == ["Buatkan puisi tentang laut"]


def test_llm_intent_is_normalized():
    parsed = ChatIntent.model_validate({"intent": "regenerate", "question_number": "2", "bloom_level": "c3"})
    assert parsed.question_number == 2
    assert parsed.bloom_level == "C3-Mengaplikasikan"


def test_generation_summary_continues_session_numbering():
    text = format_generation_summary([{"question": "A?"}, {"question": "B?"}], start_number=4)
    assert "Soal #4" in text
    assert "Soal #5" in text
    assert "Soal #1" not in text

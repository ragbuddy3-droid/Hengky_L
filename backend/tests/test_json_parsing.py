import pytest
from app.generation.question_generator import extract_json_payload, parse_questions_response, strip_reasoning_tags

def test_strip_reasoning_tags():
    text = "<think>Here is reasoning with [1] brackets</think>\n[{\"question\": \"Apa itu organ?\"}]"
    stripped = strip_reasoning_tags(text)
    assert "<think>" not in stripped
    assert stripped == "[{\"question\": \"Apa itu organ?\"}]"

def test_extract_json_with_think_tag_and_codeblock():
    text = """<think>
1. User wants 2 questions on chapter 2.
2. Context [Tarik dan Embuskan] mentions organ pernapasan.
3. Draft:
```json
[{"draft": 1}]
```
</think>

Here are the questions:
```json
[
  {
    "question": "Apa fungsi hidung?",
    "question_type": "esai",
    "answer": "Menyaring udara",
    "explanation": "Materi bab 2",
    "source_reference": "Bab 2",
    "bloom_level": "C2-Memahami"
  }
]
```"""
    parsed = parse_questions_response(text)
    assert len(parsed) == 1
    assert parsed[0]["question"] == "Apa fungsi hidung?"

def test_trailing_commas():
    text = """[
  {
    "question": "Apa nama organ pernapasan utama?",
    "question_type": "esai",
    "answer": "Paru-paru",
  },
]"""
    parsed = parse_questions_response(text)
    assert len(parsed) == 1
    assert parsed[0]["answer"] == "Paru-paru"

def test_single_dict_parsing():
    text = """{
    "question": "Berapa pasang paru-paru manusia?",
    "question_type": "esai",
    "answer": "Sepasang (2 buah)",
    "explanation": "Penjelasan",
    "source_reference": "Bab 2",
    "bloom_level": "C1-Mengingat"
}"""
    parsed = parse_questions_response(text)
    assert len(parsed) == 1
    assert parsed[0]["question"] == "Berapa pasang paru-paru manusia?"

def test_fallback_object_extraction():
    text = """Here is question 1:
{"question": "Soal 1", "answer": "Jwb 1"}
And here is question 2:
{"question": "Soal 2", "answer": "Jwb 2"}"""
    parsed = parse_questions_response(text)
    assert len(parsed) == 2
    assert parsed[0]["question"] == "Soal 1"
    assert parsed[1]["question"] == "Soal 2"

if __name__ == "__main__":
    test_strip_reasoning_tags()
    test_extract_json_with_think_tag_and_codeblock()
    test_trailing_commas()
    test_single_dict_parsing()
    test_fallback_object_extraction()
    print("ALL JSON PARSING TESTS PASSED!")

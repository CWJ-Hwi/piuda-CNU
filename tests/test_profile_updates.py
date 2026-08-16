from __future__ import annotations


def test_partial_profile_update_preserves_unspecified_fields(client, auth_headers):
    first = client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={
            "user_name": "김피움",
            "birth_year": 1952,
            "gender": "female",
            "health_context": "고혈압으로 매일 약을 복용합니다.",
            "communication_preferences": "한 번에 한 가지씩 설명해 주세요.",
            "caregiver_name": "김보호",
            "caregiver_phone": "010-1234-5678",
            "locale": "ko-KR",
        },
    )
    assert first.status_code == 200

    second = client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={"caregiver_phone": "010-9999-0000"},
    )

    assert second.status_code == 200
    profile = second.get_json()
    assert profile["user_name"] == "김피움"
    assert profile["birth_year"] == 1952
    assert profile["gender"] == "female"
    assert profile["health_context"] == "고혈압으로 매일 약을 복용합니다."
    assert profile["communication_preferences"] == "한 번에 한 가지씩 설명해 주세요."
    assert profile["caregiver_name"] == "김보호"
    assert profile["caregiver_phone"] == "010-9999-0000"
    assert profile["locale"] == "ko-KR"


def test_profile_rejects_invalid_gender_and_overlong_context(client, auth_headers):
    invalid_gender = client.put(
        "/api/v1/profile", headers=auth_headers, json={"gender": "unknown"}
    )
    overlong_context = client.put(
        "/api/v1/profile", headers=auth_headers, json={"health_context": "가" * 2001}
    )

    assert invalid_gender.status_code == 400
    assert overlong_context.status_code == 400


def test_public_profile_does_not_expose_private_llm_context(client, auth_headers):
    saved = client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={
            "health_context": "외부에 공개하지 않을 건강 정보",
            "communication_preferences": "외부에 공개하지 않을 대화 정보",
        },
    )
    public_profile = client.get("/api/v1/profile")

    assert saved.status_code == 200
    assert saved.get_json()["health_context"] == "외부에 공개하지 않을 건강 정보"
    assert public_profile.status_code == 200
    assert "health_context" not in public_profile.get_json()
    assert "communication_preferences" not in public_profile.get_json()

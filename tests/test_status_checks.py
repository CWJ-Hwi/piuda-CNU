def test_status_check_requires_caregiver_auth(client):
    response = client.post("/api/v1/status-checks")

    assert response.status_code == 401


def test_caregiver_status_check_round_trip(client, auth_headers):
    created = client.post("/api/v1/status-checks", headers=auth_headers)
    assert created.status_code == 201
    created_item = created.get_json()["item"]
    assert created.get_json()["created"] is True
    assert created_item["response"] is None

    duplicate = client.post("/api/v1/status-checks", headers=auth_headers)
    assert duplicate.status_code == 200
    assert duplicate.get_json()["created"] is False
    assert duplicate.get_json()["item"]["id"] == created_item["id"]

    pending = client.get("/api/v1/status-checks/pending")
    assert pending.status_code == 200
    assert pending.get_json()["item"]["id"] == created_item["id"]

    answered = client.post(
        f"/api/v1/status-checks/{created_item['id']}/respond",
        json={"response": "ok"},
    )
    assert answered.status_code == 200
    assert answered.get_json()["item"]["response"] == "ok"
    assert answered.get_json()["item"]["responded_at"]

    assert client.get("/api/v1/status-checks/pending").get_json()["item"] is None
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers)
    assert dashboard.status_code == 200
    assert dashboard.get_json()["status_check"]["response"] == "ok"


def test_status_check_supports_help_and_rejects_invalid_or_repeat_response(client, auth_headers):
    item = client.post("/api/v1/status-checks", headers=auth_headers).get_json()["item"]

    invalid = client.post(
        f"/api/v1/status-checks/{item['id']}/respond",
        json={"response": "maybe"},
    )
    assert invalid.status_code == 400

    answered = client.post(
        f"/api/v1/status-checks/{item['id']}/respond",
        json={"response": "help"},
    )
    assert answered.status_code == 200
    assert answered.get_json()["item"]["response"] == "help"

    repeated = client.post(
        f"/api/v1/status-checks/{item['id']}/respond",
        json={"response": "ok"},
    )
    assert repeated.status_code == 409
    assert repeated.get_json()["error"] == "already_responded"


def test_user_status_check_endpoints_are_local_network_only(client, auth_headers):
    item = client.post("/api/v1/status-checks", headers=auth_headers).get_json()["item"]
    outside = {"REMOTE_ADDR": "8.8.8.8"}

    pending = client.get("/api/v1/status-checks/pending", environ_base=outside)
    answer = client.post(
        f"/api/v1/status-checks/{item['id']}/respond",
        json={"response": "ok"},
        environ_base=outside,
    )

    assert pending.status_code == 403
    assert answer.status_code == 403

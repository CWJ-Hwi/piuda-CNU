from datetime import timedelta


def create_today_task(client, auth_headers, title):
    routine = client.post(
        "/api/v1/routines",
        headers=auth_headers,
        json={
            "title": title,
            "category": "medication",
            "scheduled_time": "13:30",
            "days_mask": 1,
        },
    )
    assert routine.status_code == 201
    tasks = client.get("/api/v1/tasks/today").get_json()["items"]
    return next(item for item in tasks if item["title"] == title)


def register_sensor(client, auth_headers):
    response = client.post(
        "/api/v1/sensors",
        headers=auth_headers,
        json={"device_uid": "confidence-room", "name": "활동 센서", "location": "거실"},
    )
    assert response.status_code == 201
    return response.get_json()


def send_event(client, sensor, event_type, occurred_at):
    response = client.post(
        "/api/v1/sensor-events",
        headers={"X-Piuda-Sensor-Key": sensor["api_key"]},
        json={
            "device_uid": sensor["device_uid"],
            "event_type": event_type,
            "occurred_at": occurred_at.isoformat(),
            "confidence": 0.9,
        },
    )
    assert response.status_code == 202


def test_completed_task_confidence_is_high_when_pir_and_csi_agree(
    client, auth_headers, fixed_now
):
    task = create_today_task(client, auth_headers, "센서로 확인할 복약")
    sensor = register_sensor(client, auth_headers)
    send_event(client, sensor, "pir_motion", fixed_now - timedelta(minutes=5))
    send_event(client, sensor, "csi_motion", fixed_now - timedelta(minutes=4))

    completed = client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    assert completed.status_code == 200
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).get_json()
    checked = next(item for item in dashboard["tasks"] if item["id"] == task["id"])

    assert checked["activity_confidence"] == "high"
    assert "PIR·CSI" in checked["activity_evidence"]


def test_completed_task_confidence_is_low_without_nearby_activity(
    client, auth_headers
):
    task = create_today_task(client, auth_headers, "근거 없는 완료")
    completed = client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    assert completed.status_code == 200

    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).get_json()
    checked = next(item for item in dashboard["tasks"] if item["id"] == task["id"])

    assert checked["activity_confidence"] == "low"
    assert "근거가 부족" in checked["activity_evidence"]


def test_pending_task_waits_for_completion_before_activity_check(client, auth_headers):
    task = create_today_task(client, auth_headers, "아직 수행 전")

    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).get_json()
    checked = next(item for item in dashboard["tasks"] if item["id"] == task["id"])

    assert checked["activity_confidence"] == "pending"
    assert "완료 기록 후" in checked["activity_evidence"]

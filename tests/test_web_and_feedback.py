from pathlib import Path


def test_web_pages_render(client):
    user = client.get("/")
    caregiver = client.get("/caregiver")
    install = client.get("/install")
    assert user.status_code == 200
    user_html = user.get_data(as_text=True)
    assert "오늘 일정" in user_html
    assert "assistant-icon" not in user_html
    assert "나의 하루 동반자" not in user_html
    assert "카메라 없이 생활 신호만 확인합니다." not in user_html
    assert caregiver.status_code == 200
    caregiver_html = caregiver.get_data(as_text=True)
    assert "보호자 확인" in caregiver_html
    assert "안전한 로컬 연결" not in caregiver_html
    assert "같은 Wi-Fi · 실시간 알림" not in caregiver_html
    assert 'href="/demo"' not in caregiver_html
    assert install.status_code == 200
    install_html = install.get_data(as_text=True)
    assert "홈 화면에 추가" in install_html
    assert "무료 로컬 웹앱 · 7일 만료 없음" not in install_html
    assert "Apple 계정 결제 없이" not in install_html


def test_pwa_assets_have_install_metadata(client):
    manifest = client.get("/manifest.webmanifest")
    caregiver_manifest = client.get("/caregiver-manifest.webmanifest")
    service_worker = client.get("/service-worker.js")

    assert manifest.status_code == 200
    assert manifest.content_type.startswith("application/manifest+json")
    assert manifest.get_json()["display"] == "standalone"
    assert manifest.get_json()["icons"][1]["purpose"] == "any maskable"
    assert caregiver_manifest.status_code == 200
    assert caregiver_manifest.get_json()["start_url"] == "/caregiver"
    assert service_worker.status_code == 200
    assert service_worker.headers["Service-Worker-Allowed"] == "/"
    assert service_worker.headers["Cache-Control"] == "no-cache"
    assert "api/" in service_worker.get_data(as_text=True)
    worker_script = service_worker.get_data(as_text=True)
    assert 'const CACHE = "piuda-v30"' in worker_script
    assert '"/static/app.css?v=30"' in worker_script
    assert '"/static/app.js?v=30"' in worker_script
    for page in ("/", "/caregiver", "/install"):
        html = client.get(page).get_data(as_text=True)
        assert '/static/app.css?v=30' in html
        assert '/static/app.js?v=30' in html
    demo_template = Path(client.application.root_path, "templates/demo.html").read_text(encoding="utf-8")
    assert '/static/app.css?v=30' in demo_template
    assert '/static/app.js?v=30' in demo_template
    assert '/static/app.css?v=30' in client.get("/static/offline.html").get_data(as_text=True)
    assert 'url.pathname === "/caregiver"' in worker_script
    assert 'fetch(event.request, { cache: "no-store" })' in worker_script
    assert '"/caregiver",' not in worker_script


def test_dynamic_ui_copy_uses_actual_state_and_risk_threshold(client):
    script = client.get("/static/app.js").get_data(as_text=True)

    assert 'element.lastChild.textContent = "연결됨"' in script
    assert "로컬 연결됨" not in script
    assert "통화 중" not in script
    assert "RTCPeerConnection" not in script
    assert 'api("/caregiver-alert", { method: "POST" })' in script
    assert "30 * 60 * 1000" in script
    assert 'needsCheck ? "점검 필요"' in script
    assert "현재 확인된 위험 요인이 없습니다." in script


def test_caregiver_shows_live_peak_delta_instead_of_wifi_strength(client):
    caregiver = client.get("/caregiver").get_data(as_text=True)
    script = client.get("/static/app.js").get_data(as_text=True)

    assert "Peak Delta" in caregiver
    assert "Peak Delta · LIVE" in script
    assert "Wi-Fi 세기" not in script
    assert "data-sensor-peak-delta" in script
    assert "refreshSensors" in script
    assert "}, 1000);" in script


def test_caregiver_can_edit_free_text_profile_and_schedule_weekdays(client):
    caregiver = client.get("/caregiver").get_data(as_text=True)
    script = client.get("/static/app.js").get_data(as_text=True)

    assert 'id="profileDialog"' in caregiver
    assert 'name="birth_year"' in caregiver
    assert 'name="gender"' in caregiver
    assert 'name="health_context"' in caregiver
    assert 'name="communication_preferences"' in caregiver
    assert 'type="checkbox" name="weekday"' in caregiver
    assert 'api("/profile", { method: "PUT", body })' in script
    assert 'form.getAll("weekday")' in script


def test_browser_media_security_policy_is_sent(client):
    response = client.get("/caregiver")
    assert response.headers["Permissions-Policy"] == "microphone=(self), camera=()"
    assert response.headers["Cache-Control"] == "no-store"


def test_caregiver_install_uses_single_http_origin(client):
    caregiver = client.get("/caregiver").get_data(as_text=True)
    install = client.get("/install").get_data(as_text=True)
    script = client.get("/static/app.js").get_data(as_text=True)

    assert "인증서" not in caregiver
    assert "음성 통화" not in caregiver
    assert "보호자 음성 통화 준비" not in install
    assert "`${origin}/caregiver`" in script
    assert "8443" not in script
    assert 'updateViaCache: "none"' in script


def test_feedback_has_safe_local_fallback(client):
    response = client.post("/api/v1/feedback", json={"message": "지금 뭘 해야 해?"})
    assert response.status_code == 200
    result = response.get_json()
    assert result["reply"]
    assert result["speak"] is True


def test_user_script_periodically_refreshes_without_http_cache(client):
    script = client.get("/static/app.js").get_data(as_text=True)
    assert 'cache: "no-store"' in script
    assert "refreshUserSnapshot" in script
    assert "}, 2000);" in script


def test_kiosk_enables_mouse_drag_scrolling_for_touch_areas(client):
    script = client.get("/static/app.js").get_data(as_text=True)

    assert '$$(".task-list, .conversation").forEach(setupMouseDragScrolling)' in script
    assert 'event.pointerType !== "mouse"' in script
    assert "element.scrollTop = startScrollTop - distance" in script


def test_pi_kiosk_uses_local_usb_microphone_endpoint(client):
    user_page = client.get("/").get_data(as_text=True)
    script = client.get("/static/app.js").get_data(as_text=True)

    assert "마이크 가까이에서 5초 안에 질문" in user_page
    assert "recordLocalVoice" in script
    assert 'api("/voice/listen", { method: "POST"' in script
    assert '$("#assistantForm").requestSubmit()' in script


def test_compact_loopback_display_uses_local_tts_and_ignores_normal_cancel_events(client):
    script = client.get("/static/app.js").get_data(as_text=True)

    assert '["127.0.0.1", "localhost"].includes(window.location.hostname)' in script
    assert 'window.matchMedia("(min-width: 821px) and (max-height: 720px)").matches' in script
    assert '["canceled", "interrupted"].includes(event.error)' in script


def test_same_wifi_demo_console_and_caregiver_alert_ui(app, client):
    app.config["DEMO_MODE"] = True
    from piuda.cli import reset_demo

    reset_demo(app)
    page = client.get("/demo").get_data(as_text=True)
    user_page = client.get("/").get_data(as_text=True)
    script = client.get("/static/app.js").get_data(as_text=True)
    assert "발표 시나리오 제어실" in page
    assert "세 장면을 순서대로 실행하면 사용자·보호자 화면이 2초 안에 갱신됩니다." in page
    assert page.count("data-trigger-scenario=") == 3
    assert "식사 지연" in page
    assert "장시간 비움" in page
    assert "넘어짐 의심" not in page
    assert 'id="caregiverAlertButton"' in user_page
    assert 'api("/caregiver-alert", { method: "POST" })' in script
    assert "triggerScenario" in script
    assert "notifyNewCaregiverAlert" in script
    assert "RTCPeerConnection" not in script
    assert 'id="userDangerDialog"' in user_page
    assert 'risk.scenario_key !== "long_absence"' in script
    assert "inactivity_check" not in script


def test_feedback_passes_recent_conversation_to_model(client, monkeypatch):
    captured = []

    def fake_feedback(message, context, history):
        captured.append((message, history))
        return "기억했어요."

    monkeypatch.setattr("piuda.api.ollama_feedback", fake_feedback)
    client.post("/api/v1/feedback", json={"message": "보리차를 마셨어요."})
    client.post("/api/v1/feedback", json={"message": "제가 뭘 마셨죠?"})

    assert captured[0][1] == []
    assert captured[1][1][-2:] == [
        {"role": "user", "content": "보리차를 마셨어요."},
        {"role": "assistant", "content": "기억했어요."},
    ]


def test_feedback_passes_saved_profile_to_model(client, auth_headers, monkeypatch):
    captured = {}

    def fake_feedback(message, context, history):
        captured.update(context)
        return "알겠습니다."

    monkeypatch.setattr("piuda.api.ollama_feedback", fake_feedback)
    saved = client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={
            "user_name": "김피움",
            "birth_year": 1952,
            "gender": "female",
            "health_context": "무릎이 불편합니다.",
            "communication_preferences": "짧고 천천히 말해 주세요.",
        },
    )
    response = client.post("/api/v1/feedback", json={"message": "오늘은 무엇을 할까요?"})

    assert saved.status_code == 200
    assert response.status_code == 200
    assert captured["profile"] == {
        "user_name": "김피움",
        "birth_year": 1952,
        "gender": "female",
        "health_context": "무릎이 불편합니다.",
        "communication_preferences": "짧고 천천히 말해 주세요.",
    }


def test_feedback_history_returns_latest_five_exchanges(client, monkeypatch):
    monkeypatch.setattr("piuda.api.ollama_feedback", lambda message, context, history: f"답변 {message}")
    for number in range(1, 7):
        response = client.post("/api/v1/feedback", json={"message": f"질문 {number}"})
        assert response.status_code == 200

    history = client.get("/api/v1/feedback/history")

    assert history.status_code == 200
    items = history.get_json()["items"]
    assert len(items) == 10
    assert items[0]["role"] == "user"
    assert items[0]["content"] == "질문 2"
    assert items[-1]["role"] == "assistant"
    assert items[-1]["content"] == "답변 질문 6"


def test_local_tts_only_accepts_loopback(client, monkeypatch):
    monkeypatch.setattr("piuda.api.speak_local_async", lambda text: bool(text))
    accepted = client.post("/api/v1/tts", json={"text": "안녕하세요."})
    denied = client.post(
        "/api/v1/tts",
        json={"text": "안녕하세요."},
        environ_overrides={"REMOTE_ADDR": "192.168.50.10"},
    )
    assert accepted.status_code == 202
    assert denied.status_code == 403

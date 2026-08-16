from __future__ import annotations

import json
from datetime import timedelta

from flask import current_app

from .clock import iso, now, parse_iso
from .db import get_db
from .risk import level_for_score


DEMO_SCENARIOS = (
    {
        "key": "normal",
        "icon": "01",
        "title": "기본 상태",
        "summary": "오늘 일정과 최근 생활 신호가 정상적으로 확인된 상태입니다.",
        "expected": "100점 · 안심 · 팝업 없음",
    },
    {
        "key": "meal_delay",
        "icon": "02",
        "title": "식사 지연",
        "summary": "점심 식사 시간이 지났고 이후 활동도 확인되지 않은 상태입니다.",
        "expected": "60점 · 주의 · 점심 식사 미수행 표시",
    },
    {
        "key": "long_absence",
        "icon": "03",
        "title": "장시간 비움",
        "summary": "PIR과 Wi-Fi CSI 생활 신호가 장시간 확인되지 않은 상태입니다.",
        "expected": "30점 · 위험 · 사용자와 보호자 양쪽 팝업",
    },
)


def scenario_catalog() -> list[dict]:
    return [dict(item) for item in DEMO_SCENARIOS]


def _scenario(key: str) -> dict | None:
    return next((dict(item) for item in DEMO_SCENARIOS if item["key"] == key), None)


def current_demo_state() -> dict:
    row = get_db().execute("SELECT * FROM demo_state WHERE id=1").fetchone()
    if row is None:
        return {
            "scenario_key": "normal",
            "scenario_title": "기본 상태",
            "description": "오늘 일정과 최근 생활 신호가 정상적으로 확인된 상태입니다.",
            "risk_score": 100,
            "risk_level": "normal",
            "factors": [],
            "user_message": "현재 확인된 위험 신호가 없습니다.",
            "activated_at": iso(),
        }
    result = dict(row)
    result["factors"] = json.loads(result.pop("factors_json"))
    return result


def _task(title: str):
    return get_db().execute(
        """
        SELECT o.id FROM task_occurrences o
        JOIN routines r ON r.id=o.routine_id
        WHERE o.due_date=? AND r.title=?
        ORDER BY o.id LIMIT 1
        """,
        (now().date().isoformat(), title),
    ).fetchone()


def _set_task(title: str, status: str) -> None:
    row = _task(title)
    if row is None:
        return
    completed_at = iso() if status == "completed" else None
    get_db().execute(
        "UPDATE task_occurrences SET status=?, completed_at=? WHERE id=?",
        (status, completed_at, row["id"]),
    )


def _sensor_id() -> int:
    row = get_db().execute("SELECT id FROM sensor_devices ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("데모 센서가 없습니다.")
    return int(row["id"])


def _clear_sensor_events() -> None:
    get_db().execute("DELETE FROM sensor_events")


def _sensor_event(event_type: str, minutes_ago: int = 0, confidence: float = 1.0, occurred_at=None) -> None:
    event_time = iso(occurred_at or (now() - timedelta(minutes=minutes_ago)))
    get_db().execute(
        """
        INSERT INTO sensor_events(device_id, event_type, value, confidence, occurred_at, received_at, payload_json)
        VALUES (?, ?, 1, ?, ?, ?, '{}')
        """,
        (_sensor_id(), event_type, confidence, event_time, iso()),
    )


def _activate(
    scenario: dict,
    score: int,
    factors: list[dict],
    user_message: str,
    alert: tuple[str, str, str] | None = None,
) -> None:
    database = get_db()
    level = level_for_score(score)
    timestamp = iso()
    factor_json = json.dumps(factors, ensure_ascii=False, separators=(",", ":"))
    database.execute(
        """
        INSERT INTO demo_state(
          id, scenario_key, scenario_title, description, risk_score,
          risk_level, factors_json, user_message, activated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          scenario_key=excluded.scenario_key,
          scenario_title=excluded.scenario_title,
          description=excluded.description,
          risk_score=excluded.risk_score,
          risk_level=excluded.risk_level,
          factors_json=excluded.factors_json,
          user_message=excluded.user_message,
          activated_at=excluded.activated_at
        """,
        (scenario["key"], scenario["title"], scenario["summary"], score, level, factor_json, user_message, timestamp),
    )
    cursor = database.execute(
        "INSERT INTO risk_assessments(score, level, factors_json, assessed_at) VALUES (?, ?, ?, ?)",
        (score, level, factor_json, timestamp),
    )
    if alert:
        alert_level, title, message = alert
        database.execute(
            "INSERT INTO alerts(risk_assessment_id, level, title, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (cursor.lastrowid, alert_level, title, message, timestamp),
        )
    database.commit()


def create_caregiver_request_alert() -> tuple[dict, bool]:
    database = get_db()
    recent = database.execute(
        "SELECT * FROM alerts WHERE title='사용자 확인 요청' AND acknowledged_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if recent and now() - parse_iso(recent["created_at"]) < timedelta(seconds=30):
        return dict(recent), False
    profile = database.execute("SELECT user_name FROM profile WHERE id=1").fetchone()
    user_name = profile["user_name"] if profile else "사용자"
    cursor = database.execute(
        "INSERT INTO alerts(risk_assessment_id, level, title, message, created_at) VALUES (NULL, 'danger', '사용자 확인 요청', ?, ?)",
        (f"{user_name}님이 보호자의 확인을 요청했습니다.", iso()),
    )
    database.commit()
    row = database.execute("SELECT * FROM alerts WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(row), True


def trigger_demo_scenario(key: str) -> dict | None:
    scenario = _scenario(key)
    if scenario is None:
        return None

    # 장면을 바꾸어도 보호자 브라우저 로그인은 유지합니다.
    from .cli import reset_demo

    reset_demo(current_app._get_current_object(), preserve_auth=True)
    if key == "normal":
        return current_demo_state()

    if key == "meal_delay":
        _set_task("점심 식사", "missed")
        factors = [
            {
                "code": "meal_missed",
                "label": "점심 식사 지연",
                "points": 15,
                "evidence": "12:30 점심 식사 미수행",
            },
            {
                "code": "scheduled_inactivity",
                "label": "식사 시간 이후 활동 미감지",
                "points": 25,
                "evidence": "식사 예정 시간 이후 생활 신호 없음",
            },
        ]
        _activate(
            scenario,
            60,
            factors,
            "점심 식사 시간이 지났어요. 식사 여부를 확인해 주세요.",
        )
    elif key == "long_absence":
        _clear_sensor_events()
        _sensor_event("pir_motion", 240, 0.98)
        factors = [
            {
                "code": "long_pir_inactivity",
                "label": "장시간 PIR 움직임 없음",
                "points": 30,
                "evidence": "마지막 움직임 4시간 전",
            },
            {
                "code": "extended_absence",
                "label": "PIR·Wi-Fi CSI 생활 신호 없음",
                "points": 40,
                "evidence": "4시간 동안 생활 신호 미확인",
            },
        ]
        _activate(
            scenario,
            30,
            factors,
            "장시간 생활 신호가 확인되지 않았어요. 보호자에게 위험 알림을 보냈습니다.",
            (
                "danger",
                "장시간 비움 위험 알림",
                "4시간 동안 PIR·Wi-Fi CSI 생활 신호가 확인되지 않았습니다. 지금 확인해 주세요.",
            ),
        )

    return current_demo_state()

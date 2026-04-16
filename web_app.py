from __future__ import annotations

import json
import os
import zlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request, session

import telegram_english_bot_latest as bot

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "replace-with-secure-secret")

STATE_FILE = Path("leaderboard.json")
try:
    SAMARA_TZ = ZoneInfo("Europe/Samara")
except ZoneInfoNotFoundError:
    # Fallback for Windows Python installs without tzdata.
    SAMARA_TZ = timezone(timedelta(hours=4))
MAX_HISTORY_MESSAGES = 120
MAX_LEADERBOARD_ROWS = 10

USER_STATES: Dict[str, Dict[str, Any]] = {}


def _today_key() -> str:
    return datetime.now(SAMARA_TZ).date().isoformat()


def _load_leaderboard() -> Dict[str, Dict[str, Any]]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        cleaned[key] = {
            "display_name": str(value.get("display_name", "User")).strip() or "User",
            "score": int(value.get("score", 0) or 0),
            "last_point_day": str(value.get("last_point_day", "")),
        }
    return cleaned


def _save_leaderboard(data: Dict[str, Dict[str, Any]]) -> None:
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _leaderboard_rows() -> List[Dict[str, Any]]:
    data = _load_leaderboard()
    rows = [
        {"display_name": item["display_name"], "score": item["score"]}
        for item in data.values()
    ]
    rows.sort(key=lambda item: (-item["score"], item["display_name"].lower()))
    return rows[:MAX_LEADERBOARD_ROWS]


def _ensure_state() -> Dict[str, Any]:
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid

    state = USER_STATES.get(sid)
    if state is None:
        state = {
            "level": None,
            "hints_enabled": True,
            "mode": "ai",
            "current_task": None,
            "fallback_scenario_idx": None,
            "last_review": None,
            "display_name": f"User {sid[:6]}",
            "telegram_user_id": None,
            "history": [],
        }
        USER_STATES[sid] = state
    return state


def _user_id() -> int:
    sid = session.get("sid", "web-user")
    return abs(zlib.crc32(sid.encode()))


def _leaderboard_key(state: Dict[str, Any]) -> str:
    telegram_id = state.get("telegram_user_id")
    if telegram_id:
        return f"tg:{telegram_id}"
    sid = session.get("sid", "web-user")
    return f"session:{sid}"


def _display_name_from_payload(data: Dict[str, Any], fallback: str) -> str:
    username = str(data.get("username", "")).strip()
    first_name = str(data.get("first_name", "")).strip()
    last_name = str(data.get("last_name", "")).strip()

    if username:
        return f"@{username}"
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or fallback


def _sync_leaderboard_profile(state: Dict[str, Any]) -> None:
    data = _load_leaderboard()
    key = _leaderboard_key(state)
    row = data.get(key, {"display_name": state["display_name"], "score": 0, "last_point_day": ""})
    row["display_name"] = state["display_name"]
    data[key] = row
    _save_leaderboard(data)


def _award_daily_point(state: Dict[str, Any]) -> bool:
    data = _load_leaderboard()
    key = _leaderboard_key(state)
    row = data.get(key, {"display_name": state["display_name"], "score": 0, "last_point_day": ""})
    row["display_name"] = state["display_name"]
    today = _today_key()
    if row.get("last_point_day") == today:
        data[key] = row
        _save_leaderboard(data)
        return False
    row["score"] = int(row.get("score", 0)) + 1
    row["last_point_day"] = today
    data[key] = row
    _save_leaderboard(data)
    return True


def _add_bot_message(state: Dict[str, Any], text: str) -> None:
    state["history"].append({"role": "bot", "text": text})
    if len(state["history"]) > MAX_HISTORY_MESSAGES:
        state["history"] = state["history"][-MAX_HISTORY_MESSAGES:]


def _add_user_message(state: Dict[str, Any], text: str) -> None:
    state["history"].append({"role": "user", "text": text})
    if len(state["history"]) > MAX_HISTORY_MESSAGES:
        state["history"] = state["history"][-MAX_HISTORY_MESSAGES:]


def _sanitize_task_for_store(task: Dict[str, str]) -> Dict[str, str]:
    return {
        "situation": task.get("situation", ""),
        "russian_text": task.get("russian_text", ""),
        "hint": task.get("hint", ""),
    }


def _generate_next_task(state: Dict[str, Any]) -> Dict[str, str]:
    level = state.get("level") or "A2"
    show_hints = bool(state.get("hints_enabled", True))
    try:
        task = bot.generate_ai_task(level)
        if not show_hints:
            task["hint"] = ""
        state["mode"] = "ai"
        state["fallback_scenario_idx"] = None
        return task
    except Exception:
        scenario = bot.next_fallback_scenario(_user_id(), level)
        state["mode"] = "fallback"
        state["fallback_scenario_idx"] = bot.FALLBACK_SCENARIOS.index(scenario)
        task = bot.build_fallback_task(scenario)
        task["hint"] = bot.build_hint_for_level(scenario, level, show_hints)
        return task


def _intro_text() -> str:
    return (
        "Привет! Я веб-версия Telegram-бота для изучения английского.\n\n"
        "Я даю задания на перевод, проверяю ответы и объясняю ошибки простым языком.\n\n"
        "Уровни:\n"
        "Легко - простые фразы и явные подсказки\n"
        "Средний - фразы средней сложности и короткие подсказки\n"
        "Сложно - более сложные фразы\n\n"
        "Кнопки:\n"
        "Выбери уровень, отвечай на фразу, затем используй «Следующее предложение»\n"
        "и «Больше информации»."
    )

def _build_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "level": state.get("level"),
        "hints_enabled": bool(state.get("hints_enabled", True)),
        "history": state.get("history", []),
        "has_current_task": bool(state.get("current_task")),
        "has_last_review": bool(state.get("last_review")),
        "display_name": state.get("display_name"),
        "leaderboard": _leaderboard_rows(),
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    state = _ensure_state()
    _sync_leaderboard_profile(state)
    if not state["history"]:
        _add_bot_message(state, _intro_text())
    return jsonify(_build_payload(state))


@app.post("/api/profile")
def api_profile():
    state = _ensure_state()
    data = request.get_json(silent=True) or {}
    telegram_user_id = data.get("telegram_user_id")
    if telegram_user_id not in (None, ""):
        state["telegram_user_id"] = str(telegram_user_id)
    state["display_name"] = _display_name_from_payload(data, state.get("display_name", "User"))
    _sync_leaderboard_profile(state)
    return jsonify(_build_payload(state))


@app.post("/api/start")
def api_start():
    state = _ensure_state()
    state["hints_enabled"] = bool(state.get("hints_enabled", True))
    state["current_task"] = None
    _sync_leaderboard_profile(state)
    _add_bot_message(state, _intro_text())
    return jsonify(_build_payload(state))


@app.post("/api/set-level")
def api_set_level():
    state = _ensure_state()
    data = request.get_json(silent=True) or {}
    level = str(data.get("level", "")).upper().strip()
    if level not in {"A1", "A2", "B1"}:
        return jsonify({"error": "Некорректный уровень"}), 400

    state["level"] = level
    state["current_task"] = None
    state["last_review"] = None
    return jsonify(_build_payload(state))


@app.post("/api/set-hints")
def api_set_hints():
    state = _ensure_state()
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", False))
    state["hints_enabled"] = enabled
    return jsonify(_build_payload(state))


@app.post("/api/next")
def api_next():
    state = _ensure_state()
    if not state.get("level"):
        _add_bot_message(state, "Сначала выбери уровень сложности.")
        return jsonify(_build_payload(state))

    _add_user_message(state, "Следующее предложение")
    _add_bot_message(state, "Подбираю следующее задание...")
    task = _generate_next_task(state)
    state["current_task"] = _sanitize_task_for_store(task)
    _add_bot_message(state, bot.build_question_text(task))
    return jsonify(_build_payload(state))


@app.post("/api/answer")
def api_answer():
    state = _ensure_state()
    data = request.get_json(silent=True) or {}
    user_text = str(data.get("text", "")).strip()
    if not user_text:
        return jsonify({"error": "РџСѓСЃС‚РѕР№ РѕС‚РІРµС‚"}), 400

    _add_user_message(state, user_text)

    if not state.get("level"):
        _add_bot_message(state, "РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРё СѓСЂРѕРІРµРЅСЊ СЃР»РѕР¶РЅРѕСЃС‚Рё.")
        return jsonify(_build_payload(state))

    task = state.get("current_task")
    if not task:
        task = _generate_next_task(state)
        state["current_task"] = _sanitize_task_for_store(task)
        _add_bot_message(state, "РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРµРј Р·Р°РґР°РЅРёРµ.\n" + bot.build_question_text(task))
        return jsonify(_build_payload(state))

    awarded_today = False
    mode = state.get("mode", "ai")
    if mode == "ai":
        try:
            review = bot.evaluate_ai_answer(state.get("level", "A2"), task, user_text)
            feedback = bot.build_ai_feedback(review)
            if bool(review.get("is_correct")):
                awarded_today = _award_daily_point(state)
            review_context = {
                "correct_translation": review.get("correct_translation", ""),
                "explanation": review.get("explanation", ""),
                "grammar_note": review.get("explanation", ""),
                "memory_tip": review.get("memory_tip", ""),
            }
        except Exception:
            idx = state.get("fallback_scenario_idx")
            if idx is None:
                scenario = bot.next_fallback_scenario(_user_id(), state.get("level", "A2"))
            else:
                scenario = bot.FALLBACK_SCENARIOS[int(idx)]
            feedback = (
                "РќРµР№СЂРѕСЃРµС‚СЊ РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅР°, РїРѕСЌС‚РѕРјСѓ СЏ РїСЂРѕРІРµСЂРёР» РѕС‚РІРµС‚ РІ Р·Р°РїР°СЃРЅРѕРј СЂРµР¶РёРјРµ.\n"
                + bot.build_fallback_feedback(user_text, scenario)
            )
            best_expected, best_score = bot.pick_best_expected(user_text, scenario.expected_answers)
            if best_score >= 0.88:
                awarded_today = _award_daily_point(state)
            review_context = {
                "correct_translation": best_expected,
                "explanation": scenario.grammar_note,
                "grammar_note": scenario.grammar_note,
                "memory_tip": scenario.memory_tip,
            }
    else:
        idx = state.get("fallback_scenario_idx")
        if idx is None:
            scenario = bot.next_fallback_scenario(_user_id(), state.get("level", "A2"))
        else:
            scenario = bot.FALLBACK_SCENARIOS[int(idx)]
        feedback = bot.build_fallback_feedback(user_text, scenario)
        best_expected, best_score = bot.pick_best_expected(user_text, scenario.expected_answers)
        if best_score >= 0.88:
            awarded_today = _award_daily_point(state)
        review_context = {
            "correct_translation": best_expected,
            "explanation": scenario.grammar_note,
            "grammar_note": scenario.grammar_note,
            "memory_tip": scenario.memory_tip,
        }

    state["last_review"] = {
        "task": _sanitize_task_for_store(task),
        "review": review_context,
    }
    state["current_task"] = None

    if awarded_today:
        feedback += "\n\n+1 РѕС‡РєРѕ РІ Р»РёРґРµСЂР±РѕСЂРґ Р·Р° РїСЂР°РІРёР»СЊРЅС‹Р№ РїРµСЂРµРІРѕРґ СЃРµРіРѕРґРЅСЏ."

    _add_bot_message(state, feedback)
    _add_bot_message(state, "Что дальше? Используй кнопки «Следующее предложение» или «Больше информации».")
    return jsonify(_build_payload(state))


@app.post("/api/more-info")
def api_more_info():
    state = _ensure_state()
    last_review = state.get("last_review")
    if not last_review:
        _add_bot_message(state, "Сначала ответь на предложение, и потом я покажу больше информации.")
        return jsonify(_build_payload(state))

    info_text = bot.build_more_info_message(last_review["task"], last_review["review"])
    _add_bot_message(state, info_text)
    return jsonify(_build_payload(state))


if __name__ == "__main__":
    app.run(debug=True)


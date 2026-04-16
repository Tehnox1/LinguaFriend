import asyncio
import difflib
import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from openai import OpenAI
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8434776565:AAEdb23_b66qTW4W0YsKWWhD-5fGoYOV5XM"
OPENAI_API_KEY = "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"
OPENAI_MODEL = "gpt-5"
STATE_FILE = Path("fallback_progress.json")
LEVEL_LABELS = {
    "A1": "Легко",
    "A2": "Средний",
    "B1": "Сложно",
}
HINT_BUTTON_TO_STATE = {
    "Подсказки: включить": True,
    "Подсказки: выключить": False,
}
MAIN_MENU_LEVEL = "Выбрать уровень сложности"
MAIN_MENU_HINTS = "Подсказки: вкл/выкл"
FOLLOW_UP_NEXT = "Следующее предложение"
FOLLOW_UP_MORE = "Больше информации"

GRAMMAR_RULES = {
    "Would like": {
        "title": "Would like для вежливой просьбы",
        "rule": (
            "Would like используем, когда хотим сказать желание или просьбу вежливо. "
            "После would like обычно идёт существительное или to + глагол."
        ),
        "pattern": "I would like + noun / I would like to + verb",
        "example": "I would like a cup of tea. / I'd like to book a room.",
        "source": "https://dictionary.cambridge.org/grammar/british-grammar/would-like",
    },
    "English modal verbs": {
        "title": "Модальные глаголы для просьб",
        "rule": (
            "Can, could, may, would помогают сделать просьбу, вопрос или предложение мягче. "
            "После модального глагола ставим обычную форму глагола без to."
        ),
        "pattern": "Could you help me? / Can I have ... ? / May I ... ?",
        "example": "Could you stop here, please?",
        "source": "https://learnenglish.britishcouncil.org/grammar/english-grammar-reference/modal-verbs",
    },
    "English questions": {
        "title": "Порядок слов в вопросах",
        "rule": (
            "В английском специальный вопрос обычно строится так: вопросительное слово, "
            "потом вспомогательный глагол, потом подлежащее и основной глагол."
        ),
        "pattern": "Wh-word + auxiliary + subject + verb",
        "example": "Where is gate five? / When does the train leave?",
        "source": "https://dictionary.cambridge.org/grammar/british-grammar/questions-wh-questions",
    },
    "Present simple": {
        "title": "Present Simple",
        "rule": (
            "Present Simple используем для фактов, привычек и регулярных действий. "
            "С he, she, it в утвердительной форме обычно добавляется -s к глаголу."
        ),
        "pattern": "I work / She works / Do you work?",
        "example": "She usually reads before bed.",
        "source": "https://learnenglish.britishcouncil.org/grammar/english-grammar-reference/talking-about-present",
    },
    "Present continuous": {
        "title": "Present Continuous",
        "rule": (
            "Present Continuous нужен для действия, которое происходит прямо сейчас "
            "или рассматривается как временное. Строится через am/is/are + глагол с -ing."
        ),
        "pattern": "am/is/are + verb-ing",
        "example": "I am waiting for my friend.",
        "source": "https://learnenglish.britishcouncil.org/node/1401",
    },
    "Present perfect": {
        "title": "Present Perfect",
        "rule": (
            "Present Perfect связывает прошлое с настоящим: действие уже произошло, "
            "и результат важен сейчас, или опыт относится к настоящему моменту."
        ),
        "pattern": "have/has + past participle",
        "example": "I have already cooked dinner. / I have never been to this city.",
        "source": "https://dictionary.cambridge.org/grammar/british-grammar/present-perfect",
    },
    "Future tense": {
        "title": "Future Simple",
        "rule": (
            "Future Simple с will используем для будущих решений, обещаний, прогнозов "
            "или нейтрального сообщения о будущем действии."
        ),
        "pattern": "will + verb",
        "example": "The movie will start in ten minutes.",
        "source": "https://learnenglish.britishcouncil.org/free-resources/grammar/english-grammar-reference/present-tense",
    },
    "Past perfect": {
        "title": "Past Perfect",
        "rule": (
            "Past Perfect показывает действие, которое завершилось раньше другого момента "
            "или действия в прошлом."
        ),
        "pattern": "had + past participle",
        "example": "By the time we arrived, the meeting had already started.",
        "source": "https://dictionary.cambridge.org/dictionary/english/past-perfect",
    },
    "First conditional": {
        "title": "First Conditional",
        "rule": (
            "First Conditional используем для реальной или возможной ситуации в будущем: "
            "в части с if обычно Present Simple, а в результате will + глагол."
        ),
        "pattern": "If + present simple, will + verb",
        "example": "If we revise the plan, we will avoid the same problems.",
        "source": "https://learnenglish.britishcouncil.org/grammar/b1-b2-grammar/conditionals-zero-first-second",
    },
    "Third conditional": {
        "title": "Third Conditional",
        "rule": (
            "Third Conditional нужен, когда мы представляем другой вариант прошлого "
            "и другой результат, который уже не случился."
        ),
        "pattern": "If + past perfect, would have + past participle",
        "example": "If you had told me earlier, I would have prepared the report.",
        "source": "https://learnenglish.britishcouncil.org/free-resources/grammar/b1-b2/conditionals-third-mixed",
    },
    "Reported speech": {
        "title": "Reported Speech",
        "rule": (
            "Reported Speech используем, когда передаём чужие слова не дословно, "
            "а пересказываем их. Часто время сдвигается назад."
        ),
        "pattern": "He said (that) ... / She asked if ...",
        "example": "The professor said that the assignment had to be submitted by Monday.",
        "source": "https://learnenglish.britishcouncil.org/grammar/english-grammar-reference/reported-speech",
    },
    "Phrasal verb": {
        "title": "Фразовые глаголы",
        "rule": (
            "Фразовый глагол состоит из основного глагола и частицы. "
            "Смысл всей конструкции часто нельзя понять только по одному глаголу."
        ),
        "pattern": "verb + particle",
        "example": "figure out, sort out, come up",
        "source": "https://dictionary.cambridge.org/grammar/british-grammar/questions-wh-questions",
    },
    "Gerund": {
        "title": "Gerund и форма на -ing",
        "rule": (
            "Форма на -ing может работать как существительное. После многих предлогов "
            "и некоторых выражений в английском употребляется именно -ing, а не to + verb."
        ),
        "pattern": "preposition + verb-ing",
        "example": "Thank you for inviting me. / She is used to working under pressure.",
        "source": "https://dictionary.cambridge.org/us/grammar/british-grammar/prepositional-",
    },
    "Used to": {
        "title": "Be used to",
        "rule": (
            "Be used to означает быть привыкшим к чему-то. После to здесь обычно идёт "
            "существительное, местоимение или форма глагола на -ing."
        ),
        "pattern": "be used to + noun / verb-ing",
        "example": "I am used to working under tight deadlines.",
        "source": "https://dictionary.cambridge.org/us/dictionary/english/be-used-to",
    },
    "English grammar": {
        "title": "Общее правило",
        "rule": (
            "Смотри на тип предложения: просьба, вопрос, привычка, действие сейчас, "
            "опыт к настоящему моменту или условие. От этого зависит время и порядок слов."
        ),
        "pattern": "situation -> grammar pattern -> translation",
        "example": "Сначала определи смысл, потом строй английскую фразу.",
        "source": "https://dictionary.cambridge.org/grammar/british-grammar/present",
    },
}


@dataclass
class Scenario:
    situation: str
    ru_prompt: str
    expected_answers: List[str]
    memory_tip: str
    grammar_note: str
    difficulty: str


FALLBACK_SCENARIOS: List[Scenario] = [
    Scenario("В кафе", "Я бы хотел чашку чая.", ["I would like a cup of tea.", "I'd like a cup of tea."], "Вежливая просьба", "После 'would like' ставим существительное или инфинитив.", "A1"),
    Scenario("В аэропорту", "Где находится выход номер пять?", ["Where is gate number five?", "Where is gate five?"], "Вопрос о месте", "В вопросе сначала 'Where is', затем объект.", "A1"),
    Scenario("В магазине", "Сколько это стоит?", ["How much does it cost?", "How much is it?"], "Вопрос о цене", "После 'does' глагол идет в начальной форме.", "A1"),
    Scenario("На улице", "Не могли бы вы мне помочь?", ["Could you help me, please?", "Could you please help me?"], "Вежливая помощь", "После 'Could you' используем глагол без -s.", "A1"),
    Scenario("Дома", "Я сейчас дома.", ["I am at home now.", "I'm at home now."], "Где я нахожусь", "Состояние часто выражаем через 'I am'.", "A1"),
    Scenario("В парке", "Погода сегодня хорошая.", ["The weather is nice today.", "The weather is good today."], "Про погоду", "После weather часто используем 'is'.", "A1"),
    Scenario("В школе", "У меня есть новый учитель.", ["I have a new teacher."], "Что у меня есть", "Для владения или наличия используем 'I have'.", "A1"),
    Scenario("В магазине", "Мне нужна бутылка воды.", ["I need a bottle of water."], "Что мне нужно", "После need можно ставить существительное.", "A1"),
    Scenario("На улице", "Я жду своего друга.", ["I am waiting for my friend.", "I'm waiting for my friend."], "Действие сейчас", "Действие сейчас часто выражаем через Present Continuous.", "A1"),
    Scenario("В кафе", "Можно меню, пожалуйста?", ["Can I have the menu, please?"], "Вежливая просьба", "Для вежливой просьбы удобно использовать 'Can I have ... ?'.", "A1"),
    Scenario("На уроке", "Я не понимаю это слово.", ["I do not understand this word.", "I don't understand this word."], "Когда не понял", "Для отрицания в Present Simple часто используем do not.", "A1"),
    Scenario("Дома", "Моя сестра на кухне.", ["My sister is in the kitchen."], "Где находится человек", "Для местоположения часто используем 'is'.", "A1"),
    Scenario("На работе", "Я отправлю письмо вечером.", ["I will send the email in the evening.", "I'll send the email in the evening."], "Будущее время", "Future Simple: 'will + глагол'.", "A2"),
    Scenario("В школе", "Она обычно читает перед сном.", ["She usually reads before going to bed.", "She usually reads before bed."], "Привычка, she", "С she/he/it добавляем окончание -s.", "A2"),
    Scenario("В такси", "Пожалуйста, остановитесь здесь.", ["Please stop here.", "Could you stop here, please?"], "Вежливая просьба", "После please глагол идет в начальной форме.", "A2"),
    Scenario("В отеле", "У меня забронирован номер.", ["I have a reservation.", "I have a room reservation."], "Бронь в отеле", "Для брони часто используют 'reservation'.", "A2"),
    Scenario("У врача", "У меня болит горло.", ["I have a sore throat."], "Самочувствие", "Для самочувствия часто используем 'I have ...'.", "A2"),
    Scenario("В автобусе", "Этот автобус идет в центр?", ["Does this bus go to the center?", "Does this bus go downtown?"], "Вопрос про маршрут", "После 'does' глагол остается в начальной форме.", "A2"),
    Scenario("В библиотеке", "Можно взять эту книгу домой?", ["Can I take this book home?"], "Разрешение", "Для простого вопроса подходит 'Can I ... ?'.", "A2"),
    Scenario("На вокзале", "Когда отправляется поезд?", ["When does the train leave?", "When does the train depart?"], "Вопрос о времени", "После 'does' не добавляем окончание -s.", "A2"),
    Scenario("На кухне", "Я уже приготовил ужин.", ["I have already cooked dinner."], "Уже сделал", "С already часто используем Present Perfect.", "A2"),
    Scenario("В кино", "Фильм начнется через десять минут.", ["The movie will start in ten minutes.", "The film will start in ten minutes."], "Будущее событие", "Для будущего события можно использовать will.", "A2"),
    Scenario("На работе", "Мы обычно начинаем в девять утра.", ["We usually start at nine in the morning.", "We usually start at nine a.m."], "Обычное действие", "Для регулярных действий используем Present Simple.", "A2"),
    Scenario("В магазине", "Я ищу черную куртку.", ["I am looking for a black jacket.", "I'm looking for a black jacket."], "Ищу вещь", "Когда действие происходит сейчас, часто используем Present Continuous.", "A2"),
    Scenario("В гостях", "Спасибо, что пригласили меня.", ["Thank you for inviting me."], "Благодарность", "После for часто используем форму с -ing.", "A2"),
    Scenario("На почте", "Мне нужно отправить эту посылку сегодня.", ["I need to send this package today.", "I need to send this parcel today."], "Нужно сделать", "После need to используем глагол в начальной форме.", "A2"),
    Scenario("На занятии", "Мы обсуждаем важную тему.", ["We are discussing an important topic.", "We're discussing an important topic."], "Действие сейчас", "Для действия в момент речи часто используем Present Continuous.", "A2"),
    Scenario("У друга", "Я никогда не был в этом городе.", ["I have never been to this city.", "I've never been to this city."], "Опыт в жизни", "Для опыта в жизни часто используем Present Perfect.", "A2"),
    Scenario("На собеседовании", "Я работаю в этой компании два года.", ["I have worked at this company for two years.", "I have been working at this company for two years."], "Срок действия", "Для действия, которое началось раньше и идет сейчас, часто используем Present Perfect.", "B1"),
    Scenario("С друзьями", "Давай закажем что-нибудь сладкое.", ["Let's order something sweet."], "Совместное решение", "Для совместного предложения используем 'Let's + глагол'.", "B1"),
    Scenario("На совещании", "Если бы ты предупредил меня раньше, я бы подготовил отчет.", ["If you had told me earlier, I would have prepared the report."], "Условие в прошлом", "Для нереального прошлого часто используем Third Conditional.", "B1"),
    Scenario("В офисе", "К тому времени, как мы пришли, встреча уже началась.", ["By the time we arrived, the meeting had already started."], "Два действия в прошлом", "Для более раннего прошлого действия часто используем Past Perfect.", "B1"),
    Scenario("В университете", "Мне нужно разобраться в этом вопросе до пятницы.", ["I need to figure this issue out by Friday.", "I need to sort this issue out by Friday."], "Фразовый глагол", "После need to используем глагол в начальной форме.", "B1"),
    Scenario("В переписке", "Буду признателен, если вы ответите как можно скорее.", ["I would appreciate it if you replied as soon as possible."], "Вежливая деловая речь", "Для вежливой деловой просьбы часто используем 'I would appreciate it if ...'.", "B1"),
    Scenario("В путешествии", "Несмотря на задержку, нам удалось успеть на пересадку.", ["Despite the delay, we managed to catch our connection."], "Уступка", "После despite ставим существительное или герундий.", "B1"),
    Scenario("На работе", "Я привык работать в условиях жестких сроков.", ["I am used to working under tight deadlines."], "Привычка к условиям", "После 'be used to' часто идет форма с -ing.", "B1"),
    Scenario("На конференции", "К тому моменту, как докладчик закончил, аудитория уже начала задавать вопросы.", ["By the time the speaker finished, the audience had already started asking questions."], "Past Perfect", "Для более раннего прошлого используем Past Perfect.", "B1"),
    Scenario("В проекте", "Если мы не пересмотрим план, можем столкнуться с теми же проблемами снова.", ["If we do not revise the plan, we may run into the same problems again.", "If we don't revise the plan, we may run into the same problems again."], "Условие и результат", "В First Conditional часто используем Present Simple в условии.", "B1"),
    Scenario("В деловой переписке", "Я хотел бы уточнить, получили ли вы документы, которые я отправил вчера.", ["I would like to clarify whether you received the documents I sent yesterday."], "Уточнение", "В деловой речи часто используем 'I would like to clarify whether ...'.", "B1"),
    Scenario("На учебе", "Чем больше я практикуюсь, тем увереннее чувствую себя во время разговора.", ["The more I practice, the more confident I feel when speaking."], "The more..., the more...", "Сравнительную зависимость часто строим через 'The more..., the more...'.", "B1"),
    Scenario("На работе", "Мне пришлось перенести встречу, потому что возникли непредвиденные обстоятельства.", ["I had to postpone the meeting because unexpected circumstances came up."], "Пришлось сделать", "Для вынужденного действия в прошлом часто используем 'had to'.", "B1"),
    Scenario("В поездке", "Если бы рейс не задержали, мы бы уже заселились в отель.", ["If the flight had not been delayed, we would have already checked into the hotel."], "Нереальное прошлое", "Для нереальной ситуации в прошлом используем Third Conditional.", "B1"),
    Scenario("В университете", "Преподаватель сказал, что работа должна быть сдана не позднее понедельника.", ["The professor said that the assignment had to be submitted no later than Monday."], "Косвенная речь", "В косвенной речи время часто сдвигается назад.", "B1"),
    Scenario("На встрече", "Хотя предложение звучало убедительно, у нас все еще были серьезные сомнения.", ["Although the proposal sounded convincing, we still had serious doubts."], "Хотя...", "После although ставим полное предложение.", "B1"),
]

TASK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "situation": {"type": "string"},
        "russian_text": {"type": "string"},
        "hint": {"type": "string"},
    },
    "required": ["situation", "russian_text", "hint"],
}

CHECK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_correct": {"type": "boolean"},
        "score": {"type": "integer"},
        "correct_translation": {"type": "string"},
        "mistakes": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
        "memory_tip": {"type": "string"},
        "encouragement": {"type": "string"},
    },
    "required": [
        "is_correct",
        "score",
        "correct_translation",
        "mistakes",
        "explanation",
        "memory_tip",
        "encouragement",
    ],
}


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def pick_best_expected(user_answer: str, expected_answers: List[str]) -> Tuple[str, float]:
    normalized_user = normalize_text(user_answer)
    best_answer = expected_answers[0]
    best_score = 0.0
    for candidate in expected_answers:
        score = similarity(normalized_user, normalize_text(candidate))
        if score > best_score:
            best_score = score
            best_answer = candidate
    return best_answer, best_score


def token_feedback(user_answer: str, expected_answer: str) -> Dict[str, List[str]]:
    user_tokens = normalize_text(user_answer).split()
    expected_tokens = normalize_text(expected_answer).split()
    missing = [token for token in expected_tokens if token not in user_tokens]
    extra = [token for token in user_tokens if token not in expected_tokens]
    return {"missing": missing, "extra": extra}


def load_state() -> Dict[str, List[int]]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cleaned: Dict[str, List[int]] = {}
    for user_id, indices in data.items():
        if isinstance(indices, list):
            cleaned[user_id] = [index for index in indices if isinstance(index, int)]
    return cleaned


def save_state(state: Dict[str, List[int]]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def level_rank(level: str) -> int:
    return {"A1": 1, "A2": 2, "B1": 3}.get(level, 2)


def hints_enabled(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.user_data.get("hints_enabled", True)


def build_hint_for_level(scenario: Scenario, level: str, enabled: bool) -> str:
    if not enabled:
        return ""
    return scenario.memory_tip


def next_fallback_scenario(user_id: int, level: str) -> Scenario:
    state = load_state()
    key = f"{user_id}:{level}"
    used = state.get(key, [])
    allowed = [
        index for index, scenario in enumerate(FALLBACK_SCENARIOS)
        if scenario.difficulty == level
    ]

    available = [index for index in allowed if index not in used]

    if not available:
        used = []
        available = allowed

    chosen_index = random.choice(available)
    used.append(chosen_index)
    state[key] = used
    save_state(state)
    return FALLBACK_SCENARIOS[chosen_index]


def create_openai_client() -> OpenAI:
    key = OPENAI_API_KEY.strip()
    if not key or key == "PASTE_YOUR_OPENAI_API_KEY_HERE":
        raise RuntimeError("Укажи OpenAI API ключ в OPENAI_API_KEY.")
    return OpenAI(api_key=key)


def parse_json_output(response) -> Dict:
    text = getattr(response, "output_text", "").strip()
    if not text:
        raise ValueError("Модель не вернула JSON.")
    return json.loads(text)


def generate_ai_task(level: str) -> Dict[str, str]:
    client = create_openai_client()
    level_rules = {
        "A1": "Дай очень простую бытовую фразу. Подсказка может быть чуть более явной.",
        "A2": "Дай фразу средней сложности. Подсказка должна быть короткой и не слишком очевидной.",
        "B1": "Дай заметно более сложную фразу с более продвинутой грамматикой или лексикой. Подсказку не давай.",
    }
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "Ты преподаватель английского для русскоязычных учеников. "
            "Сгенерируй одно жизненное задание на перевод с русского на английский. "
            + level_rules.get(level, level_rules["A2"]) + " "
            + "Если уровень B1, поле hint верни пустой строкой. "
            + "Если уровень не B1, подсказка должна быть короткой. "
            "Верни только JSON."
        ),
        input=f"Уровень ученика: {level}. Придумай новое задание.",
        text={
            "format": {
                "type": "json_schema",
                "name": "english_task",
                "schema": TASK_SCHEMA,
                "strict": True,
            }
        },
    )
    return parse_json_output(response)


def evaluate_ai_answer(level: str, task: Dict[str, str], user_answer: str) -> Dict:
    client = create_openai_client()
    memory_hint_rule = (
        "Подсказку для памяти не давай."
        if level == "B1"
        else "Подсказку для памяти сделай короткой: 2-6 слов."
    )
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "Ты доброжелательный преподаватель английского языка. "
            "Проверь перевод гибко и справедливо. "
            + memory_hint_rule + " "
            "Верни только JSON."
        ),
        input=(
            f"Уровень ученика: {level}\n"
            f"Ситуация: {task['situation']}\n"
            f"Русская фраза: {task['russian_text']}\n"
            f"Подсказка: {task['hint']}\n"
            f"Ответ ученика: {user_answer}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "translation_review",
                "schema": CHECK_SCHEMA,
                "strict": True,
            }
        },
    )
    return parse_json_output(response)


def build_fallback_task(scenario: Scenario) -> Dict[str, str]:
    return {
        "situation": scenario.situation,
        "russian_text": scenario.ru_prompt,
        "hint": scenario.memory_tip,
    }


def build_question_text(task: Dict[str, str]) -> str:
    hint = task.get("hint", "").strip()
    hint_text = f"\nПодсказка: {hint}" if hint else ""
    return (
        f"Ситуация: {task['situation']}\n"
        f"Переведи на английский:\n"
        f"«{task['russian_text']}»"
        f"{hint_text}\n\n"
        "Напиши свой перевод одним сообщением."
    )


async def get_next_task(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Dict[str, str]:
    level = context.user_data.get("level", "A2")
    show_hints = hints_enabled(context)
    try:
        task = await asyncio.to_thread(generate_ai_task, level)
        if not show_hints:
            task["hint"] = ""
        context.user_data["mode"] = "ai"
        context.user_data["fallback_scenario"] = None
        return task
    except Exception as exc:
        logger.exception("AI task generation failed: %s", exc)
        scenario = next_fallback_scenario(user_id, level)
        context.user_data["mode"] = "fallback"
        context.user_data["fallback_scenario"] = scenario
        task = build_fallback_task(scenario)
        task["hint"] = build_hint_for_level(scenario, level, show_hints)
        return task


def build_fallback_feedback(user_answer: str, scenario: Scenario) -> str:
    best_expected, best_score = pick_best_expected(user_answer, scenario.expected_answers)
    details = token_feedback(user_answer, best_expected)

    if best_score >= 0.88:
        return (
            "Отлично! Очень хороший перевод.\n"
            f"Один из правильных вариантов: {best_expected}\n"
            f"Запоминалка: {scenario.memory_tip}"
        )

    if best_score >= 0.70:
        parts = [
            "Неплохо! Смысл близкий, но есть мелкие ошибки.",
            f"Лучший вариант: {best_expected}",
        ]
        if details["missing"]:
            parts.append("Не хватает слов: " + ", ".join(details["missing"]))
        if details["extra"]:
            parts.append("Лишние или спорные слова: " + ", ".join(details["extra"]))
        parts.append("Объяснение: " + scenario.grammar_note)
        parts.append("Запоминалка: " + scenario.memory_tip)
        return "\n".join(parts)

    parts = [
        "Пока не совсем правильно, но это нормально - учимся шаг за шагом.",
        f"Правильный перевод: {best_expected}",
    ]
    if details["missing"]:
        parts.append("Что важно добавить: " + ", ".join(details["missing"]))
    if details["extra"]:
        parts.append("Что лучше убрать или заменить: " + ", ".join(details["extra"]))
    parts.append("Почему так: " + scenario.grammar_note)
    parts.append("Как запомнить: " + scenario.memory_tip)
    return "\n".join(parts)


def build_ai_feedback(review: Dict) -> str:
    parts = [review["encouragement"], f"Оценка: {review['score']}/100"]
    parts.append(f"Правильный вариант: {review['correct_translation']}")
    if review["mistakes"]:
        parts.append("Что исправить: " + "; ".join(review["mistakes"]))
    parts.append("Объяснение: " + review["explanation"])
    if review["memory_tip"].strip():
        parts.append("Как запомнить: " + review["memory_tip"])
    return "\n".join(parts)


def detect_grammar_topic(text: str) -> str:
    lowered = text.lower()
    topic_map = [
        ("present perfect", "Present perfect"),
        ("past perfect", "Past perfect"),
        ("third conditional", "Third conditional"),
        ("first conditional", "First conditional"),
        ("present continuous", "Present continuous"),
        ("present simple", "Present simple"),
        ("future simple", "Future tense"),
        ("reported speech", "Reported speech"),
        ("phrasal verb", "Phrasal verb"),
        ("gerund", "Gerund"),
        ("would like", "Would like"),
        ("be used to", "Used to"),
        ("question", "English questions"),
    ]
    for needle, topic in topic_map:
        if needle in lowered:
            return topic

    if "could you" in lowered or "please" in lowered:
        return "English modal verbs"
    if "if " in lowered and "would have" in lowered:
        return "Third conditional"
    if "if " in lowered and "may" in lowered:
        return "First conditional"
    if "already" in lowered or "never been" in lowered:
        return "Present perfect"
    if "by the time" in lowered or "had " in lowered:
        return "Past perfect"
    if "am " in lowered and "ing" in lowered:
        return "Present continuous"
    return "English grammar"


def build_more_info_message(task: Dict[str, str], review_context: Dict[str, str]) -> str:
    base_text = " ".join(
        [
            task.get("russian_text", ""),
            review_context.get("correct_translation", ""),
            review_context.get("explanation", ""),
            review_context.get("grammar_note", ""),
            review_context.get("memory_tip", ""),
        ]
    )
    topic = detect_grammar_topic(base_text)
    rule = GRAMMAR_RULES.get(topic, GRAMMAR_RULES["English grammar"])
    return (
        "Больше информации по этой фразе:\n"
        f"Тема: {rule['title']}\n"
        f"Правило: {rule['rule']}\n"
        f"Схема: {rule['pattern']}\n"
        f"Пример: {rule['example']}\n"
        f"Источник: {rule['source']}"
    )


LEVEL_1_BUTTON = "1. Простой уровень"
LEVEL_2_BUTTON = "2. Средний уровень"
LEVEL_3_BUTTON = "3. Сложный уровень"

LEVEL_BUTTON_TO_CODE = {
    LEVEL_1_BUTTON: "A1",
    LEVEL_2_BUTTON: "A2",
    LEVEL_3_BUTTON: "B1",
}


def build_level_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(LEVEL_1_BUTTON)],
            [KeyboardButton(LEVEL_2_BUTTON)],
            [KeyboardButton(LEVEL_3_BUTTON)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_hints_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("\u041f\u043e\u0434\u0441\u043a\u0430\u0437\u043a\u0438: \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c")],
            [KeyboardButton("Подсказки: выключить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(MAIN_MENU_LEVEL)],
            [KeyboardButton(MAIN_MENU_HINTS)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_follow_up_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(FOLLOW_UP_NEXT)],
            [KeyboardButton(FOLLOW_UP_MORE)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_next_only_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(FOLLOW_UP_NEXT)]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def is_control_text(text: str) -> bool:
    return text in {
        MAIN_MENU_LEVEL,
        MAIN_MENU_HINTS,
        FOLLOW_UP_NEXT,
        FOLLOW_UP_MORE,
        *LEVEL_BUTTON_TO_CODE.keys(),
        *HINT_BUTTON_TO_STATE.keys(),
    }


async def send_level_prompt(message_target) -> None:
    await message_target.reply_text(
        "Выбери уровень для дальнейшей переписки:",
        reply_markup=build_level_keyboard(),
    )


async def send_hints_prompt(message_target) -> None:
    await message_target.reply_text(
        "Выбери режим подсказок:",
        reply_markup=build_hints_keyboard(),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["hints_enabled"] = context.user_data.get("hints_enabled", True)
    intro_text = (
        "Привет! Я Telegram-бот для изучения английского.\n\n"
        "Я даю задания на перевод, проверяю ответы и объясняю ошибки простым языком.\n\n"
        "Уровни:\n"
        "Легко - простые фразы и явные подсказки\n"
        "Средний - фразы средней сложности и короткие подсказки\n"
        "Сложно - более сложные фразы\n\n"
        "Команды:\n"
        "/start - начать\n"
        "/next - новое задание\n"
        "/menu - открыть меню(выбор сложности и вкл/выкл подсказки).\n"
    )
    await update.message.reply_text(intro_text)
    context.user_data.pop("current_task", None)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Меню:",
        reply_markup=build_main_menu(),
    )


async def level_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_level_prompt(update.message)


async def hints_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_hints_prompt(update.message)


async def choose_level_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected = (update.message.text or "").strip()
    level = LEVEL_BUTTON_TO_CODE.get(selected)
    if not level:
        if selected.startswith("1"):
            level = "A1"
        elif selected.startswith("2"):
            level = "A2"
        elif selected.startswith("3"):
            level = "B1"
    if not level:
        await update.message.reply_text(
            "Не удалось определить уровень. Попробуй выбрать кнопку ещё раз.",
            reply_markup=build_level_keyboard(),
        )
        return

    logger.info("Level selected from keyboard: %s by user %s", level, update.effective_user.id)
    context.user_data["level"] = level
    context.user_data.pop("current_task", None)

    await update.message.reply_text(
        f"Текущий уровень: {LEVEL_LABELS[level]}. Подбираю первое задание...",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        task = await get_next_task(context, update.effective_user.id)
        context.user_data["current_task"] = task
        await update.message.reply_text(build_question_text(task))
    except Exception as exc:
        logger.exception("Failed to prepare first task after level selection: %s", exc)
        await update.message.reply_text(
            "Уровень выбран, но первое задание сейчас не загрузилось. Попробуй /next.",
        )


async def choose_hints_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected = (update.message.text or "").strip()
    enabled = HINT_BUTTON_TO_STATE.get(selected)
    if enabled is None:
        await update.message.reply_text(
            "Не удалось определить режим подсказок. Попробуй выбрать кнопку ещё раз.",
            reply_markup=build_hints_keyboard(),
        )
        return

    context.user_data["hints_enabled"] = enabled
    status_text = "включены" if enabled else "выключены"
    await update.message.reply_text(
        f"Подсказки {status_text}.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected = (update.message.text or "").strip()
    if selected == MAIN_MENU_LEVEL:
        await send_level_prompt(update.message)
        return
    if selected == MAIN_MENU_HINTS:
        await send_hints_prompt(update.message)
        return


async def handle_follow_up_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected = (update.message.text or "").strip()
    if selected == FOLLOW_UP_NEXT:
        await update.message.reply_text(
            "Подбираю следующее задание...",
            reply_markup=ReplyKeyboardRemove(),
        )
        task = await get_next_task(context, update.effective_user.id)
        context.user_data["current_task"] = task
        await update.message.reply_text(build_question_text(task))
        return

    if selected != FOLLOW_UP_MORE:
        return

    last_review = context.user_data.get("last_review")
    if not last_review:
        await update.message.reply_text(
            "Сначала ответь на предложение, и потом я смогу показать больше информации.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text(
        "Показываю правило по этой фразе...",
        reply_markup=ReplyKeyboardRemove(),
    )
    info_text = await asyncio.to_thread(
        build_more_info_message,
        last_review["task"],
        last_review["review"],
    )
    await update.message.reply_text(
        info_text,
        reply_markup=build_next_only_keyboard(),
    )


async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("level"):
        await send_level_prompt(update.message)
        return
    await update.message.reply_text("Подбираю следующее задание...")
    task = await get_next_task(context, update.effective_user.id)
    context.user_data["current_task"] = task
    await update.message.reply_text(build_question_text(task))


async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("level"):
        await send_level_prompt(update.message)
        return

    user_text = (update.message.text or "").strip()
    if is_control_text(user_text):
        return
    task = context.user_data.get("current_task")

    if not task:
        task = await get_next_task(context, update.effective_user.id)
        context.user_data["current_task"] = task
        await update.message.reply_text("Сначала выберем задание.\n" + build_question_text(task))
        return

    mode = context.user_data.get("mode", "ai")
    if mode == "ai":
        try:
            review = await asyncio.to_thread(
                evaluate_ai_answer,
                context.user_data.get("level", "A2"),
                task,
                user_text,
            )
            feedback = build_ai_feedback(review)
            review_context = {
                "correct_translation": review.get("correct_translation", ""),
                "explanation": review.get("explanation", ""),
                "grammar_note": review.get("explanation", ""),
                "memory_tip": review.get("memory_tip", ""),
            }
        except Exception as exc:
            logger.exception("AI answer evaluation failed: %s", exc)
            scenario = context.user_data.get("fallback_scenario") or next_fallback_scenario(
                update.effective_user.id,
                context.user_data.get("level", "A2"),
            )
            feedback = (
                "Нейросеть временно недоступна, поэтому я проверил ответ в запасном режиме.\n"
                + build_fallback_feedback(user_text, scenario)
            )
            review_context = {
                "correct_translation": scenario.expected_answers[0],
                "explanation": scenario.grammar_note,
                "grammar_note": scenario.grammar_note,
                "memory_tip": scenario.memory_tip,
            }
    else:
        scenario = context.user_data.get("fallback_scenario") or next_fallback_scenario(
            update.effective_user.id,
            context.user_data.get("level", "A2"),
        )
        feedback = build_fallback_feedback(user_text, scenario)
        review_context = {
            "correct_translation": scenario.expected_answers[0],
            "explanation": scenario.grammar_note,
            "grammar_note": scenario.grammar_note,
            "memory_tip": scenario.memory_tip,
        }

    context.user_data["last_review"] = {
        "task": {
            "situation": task.get("situation", ""),
            "russian_text": task.get("russian_text", ""),
            "hint": task.get("hint", ""),
        },
        "review": review_context,
    }
    context.user_data.pop("current_task", None)

    await update.message.reply_text(feedback)
    await update.message.reply_text(
        "Что дальше?",
        reply_markup=build_follow_up_keyboard(),
    )


async def route_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text_value = (update.message.text or "").strip()

    if text_value in LEVEL_BUTTON_TO_CODE or text_value.startswith(("1", "2", "3")):
        await choose_level_from_text(update, context)
        return

    if text_value in HINT_BUTTON_TO_STATE:
        await choose_hints_from_text(update, context)
        return

    if text_value in {MAIN_MENU_LEVEL, MAIN_MENU_HINTS}:
        await handle_main_menu(update, context)
        return

    if text_value in {FOLLOW_UP_NEXT, FOLLOW_UP_MORE}:
        await handle_follow_up_buttons(update, context)
        return

    await check_answer(update, context)


def main() -> None:
    token = BOT_TOKEN.strip()
    if not token:
        raise RuntimeError("Укажи токен Telegram-бота в BOT_TOKEN.")

    asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("next", next_question))
    app.add_handler(CommandHandler("level", level_menu))
    app.add_handler(CommandHandler("hints", hints_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text_message))

    logger.info("Latest bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

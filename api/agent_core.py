from __future__ import annotations

"""
Agent Core v1 для TG Hub.

ARCH:
- НЕ меняет модель LLM и существующий API /api/chat снаружи.
- Добавляет тонкий слой управления между /api/chat и ai_client.chat:
  - AgentState (persona, память, последние действия)
  - Intent/Decision перед вызовом LLM
  - обновление памяти после ответа.

AgentCore НЕ знает про FastAPI / HTTP. Его задача — работать с user_id, текстом
и вспомогательными данными (контекстом) и возвращать:
  - intent / decision
  - расширенный системный промпт
  - обновлённый AgentState.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import aiosqlite
import json

from .services.ai_client import chat as ai_chat, AiNotConfiguredError


@dataclass
class AgentState:
    """Минимальное устойчивое состояние агента для пользователя."""

    user_id: str
    persona: str
    active_goals: List[str] = field(default_factory=list)
    recent_actions: List[str] = field(default_factory=list)
    memory_summary: str = ""


DEFAULT_PERSONA = (
    "Ты — личный ассистент YouHub: спокойный, тактичный, говоришь по-русски, "
    "объясняешь просто, без высокомерия и паники. Ты не эксперт-консультант, "
    "а умный помощник, который помогает навести порядок в делах, деньгах и "
    "отношениях. Отвечаешь коротко, по делу, как человек, который хорошо "
    "знает пользователя и его контекст."
)


class AgentCore:
    """
    Управляющий слой между API / данными и LLM.

    Задачи:
    - хранить/обновлять AgentState в БД (таблица agent_state);
    - делать простой Intent + Decision;
    - расширять системный промпт персоной и памятью;
    - сохранять краткое резюме после каждого ответа (Memory Writer).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # --- Работа с состоянием -------------------------------------------------

    async def load_state(self, user_id: str) -> AgentState:
        """Загрузить AgentState из БД или создать дефолтное состояние."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT persona, active_goals, recent_actions, memory_summary
                FROM agent_state
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return AgentState(user_id=user_id, persona=DEFAULT_PERSONA)

            def _loads(val: Optional[str]) -> List[str]:
                if not val:
                    return []
                try:
                    data = json.loads(val)
                    return [str(x) for x in data] if isinstance(data, list) else []
                except Exception:
                    return []

            return AgentState(
                user_id=user_id,
                persona=row["persona"] or DEFAULT_PERSONA,
                active_goals=_loads(row["active_goals"]),
                recent_actions=_loads(row["recent_actions"]),
                memory_summary=row["memory_summary"] or "",
            )

    async def save_state(self, state: AgentState) -> None:
        """Сохранить AgentState в БД (upsert по user_id)."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO agent_state (user_id, persona, active_goals, recent_actions, memory_summary)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    persona = excluded.persona,
                    active_goals = excluded.active_goals,
                    recent_actions = excluded.recent_actions,
                    memory_summary = excluded.memory_summary
                """,
                (
                    state.user_id,
                    state.persona,
                    json.dumps(state.active_goals, ensure_ascii=False),
                    json.dumps(state.recent_actions[-10:], ensure_ascii=False),
                    state.memory_summary,
                ),
            )
            await db.commit()

    # --- Intent / Decision ---------------------------------------------------

    def analyze_intent(self, message: str, direct_command: Optional[Dict[str, Any]] = None) -> str:
        """
        Очень простой анализ намерения.

        Возвращает один из:
        - direct_action
        - finance_question
        - tasks_question
        - planning
        - question
        - smalltalk
        """
        msg = (message or "").strip().lower()
        if direct_command:
            return "direct_action"
        if any(word in msg for word in ("баланс", "расход", "расходы", "доход", "доходы", "деньги", "финанс")):
            return "finance_question"
        if any(word in msg for word in ("задач", "список дел", "дела", "план на", "приорит")):
            return "tasks_question"
        if "план" in msg or "список дел" in msg or "приорит" in msg:
            return "planning"
        if "?" in msg or msg.startswith(("почему", "как ", "что ", "зачем")):
            return "question"
        return "smalltalk"

    def build_system_prompt(
        self,
        base_prompt: str,
        state: AgentState,
        intent: str,
    ) -> str:
        """
        Расширяет базовый промпт личностью и памятью агента.

        base_prompt — то, что уже формирует API (данные пользователя, правила).
        """
        goals_text = ", ".join(state.active_goals[:5]) if state.active_goals else "нет зафиксированных целей"
        recent_text = "; ".join(state.recent_actions[-5:]) if state.recent_actions else "пока нет явных действий агента"
        memory = state.memory_summary or "память пока пуста; агент только начинает изучать пользователя"

        prefix = f"""Твоя устойчивая личность (persona):
{state.persona}

Память агента (краткие выводы, а не полный чат):
{memory}

Активные цели пользователя по версии агента:
{goals_text}

Последние решения/действия агента:
{recent_text}

Текущее намерение пользователя (черновая оценка): {intent}.

Далее идут структурированные данные пользователя и правила ответа:
"""
        return prefix + "\n" + base_prompt

    # --- Memory Writer -------------------------------------------------------

    async def update_memory_after_turn(
        self,
        state: AgentState,
        user_message: str,
        assistant_reply: str,
        decision: str,
    ) -> AgentState:
        """
        Обновляет memory_summary и recent_actions после хода диалога.

        LLM вызывается в режиме резюме (1 короткое предложение),
        на безопасном маленьком промпте.
        """
        # Обновляем recent_actions (ограничиваем 10 последних)
        summary_action = f"{decision}: '{user_message[:80]}' -> '{assistant_reply[:80]}'"
        state.recent_actions.append(summary_action)
        state.recent_actions = state.recent_actions[-10:]

        # Если AI не настроен — просто сохраняем recent_actions как есть
        try:
            prompt = """Ты — внутренний модуль памяти ассистента YouHub.
На входе:
- предыдущая краткая память агента (1–2 предложения)
- последнее сообщение пользователя
- последний ответ ассистента

Задача:
- верни ОДНО предложение на русском, которое лучше всего описывает,
  что стоит запомнить про пользователя или его ситуацию в долгую.
- не повторяй детали чата, даты и суммы, только устойчивые предпочтения и паттерны.
"""
            messages = [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"Предыдущая память: {state.memory_summary or 'нет'}\n"
                    f"Сообщение пользователя: {user_message}\n"
                    f"Ответ ассистента: {assistant_reply}",
                },
            ]
            new_memory = await ai_chat(
                messages,
                model_hint="summary",
                max_tokens=80,
                temperature=0.2,
            )
            if new_memory:
                state.memory_summary = new_memory.strip()
        except AiNotConfiguredError:
            # Оставляем прошлую память как есть
            pass
        except Exception:
            # Не роняем диалог из-за внутренней ошибки памяти
            pass

        return state


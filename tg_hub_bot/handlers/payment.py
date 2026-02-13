"""
Оплата Telegram Stars — доступ к YouHub.

До /start показываем invoice. После успешной оплаты — приветствие.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery

from config import PAYMENT_STARS
from storage.bootstrap import get_paid_repo

logger = logging.getLogger(__name__)

PAYLOAD_ACCESS = "youhub_access"


async def send_invoice(bot: Bot, chat_id: int, user_id: str) -> None:
    """Отправляет invoice на оплату доступа (~100 ₽ в Stars)."""
    await bot.send_invoice(
        chat_id=chat_id,
        title="YouHub — твой хаб для дел и денег",
        description=(
            "Забудь про потерянные задачи и разлетевшийся бюджет. YouHub — всё в одном: "
            "задачи, проекты, финансы, картотека. Пиши — бот поймёт и сделает. "
            "ИИ-помощник, напоминания, сводки. Разово — навсегда."
        ),
        payload=PAYLOAD_ACCESS,
        provider_token="",  # Stars — пустой токен
        currency="XTR",
        prices=[LabeledPrice(label="Полный доступ к YouHub", amount=PAYMENT_STARS)],
    )


def register_payment_handlers(
    dp: Dispatcher,
    bot: Bot,
    webapp_url: str | None,
) -> None:
    """Регистрирует pre_checkout и successful_payment."""

    @dp.pre_checkout_query(F.invoice_payload == PAYLOAD_ACCESS)
    async def pre_checkout(query: PreCheckoutQuery) -> None:
        await query.answer(ok=True)

    @dp.message(F.successful_payment)
    async def successful_payment(message: Message) -> None:
        if not message.from_user:
            return
        if message.successful_payment.invoice_payload != PAYLOAD_ACCESS:
            return

        user_id = str(message.from_user.id)
        charge_id = message.successful_payment.telegram_payment_charge_id

        paid_repo = get_paid_repo()
        await paid_repo.mark_paid(user_id, charge_id)

        logger.info("Оплата получена: user_id=%s", user_id)
        from tg_hub_bot.handlers.start import _send_welcome
        await _send_welcome(bot, message.chat.id, webapp_url)

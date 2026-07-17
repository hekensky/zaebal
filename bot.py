"""
Telegram-бот "Журнал трейдера".

Возможности:
- Заводить новую позицию: тикер, направление, ТВХ, стоп-лосс, тейк-профит,
  комментарий "почему открываю".
- Раздел "Активные позиции" — сделки, которые ещё не достигли тейка/стопа.
  Для каждой можно отметить исход:
    * Закрылась по тейку -> просим скрин PnL + комментарий (по умолчанию "победная" фраза)
    * Закрылась по стопу -> просим скрин PnL + комментарий, почему не отработало
    * Не дошло до ТВХ    -> просим комментарий, почему цена не дошла (без скрина)
- Раздел "История" — все закрытые сделки с пагинацией.
- Раздел "Статистика" — количество сделок, винрейт, плановый R/R.

Запуск:
    pip install -r requirements.txt
    cp .env.example .env   # и вписать туда токен бота
    python bot.py
"""

import asyncio
import logging
import os
import random

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums.parse_mode import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.markdown import escape_html
from dotenv import load_dotenv

import database as db
import keyboards as kb
from states import ClosePosition, MissedPosition, NewPosition

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "journal.db")

logging.basicConfig(level=logging.INFO)
router = Router()

VICTORY_PHRASES = [
    "🎉 Победа! План сработал точно как задумано.",
    "💪 Отличная сделка, дисциплина окупается!",
    "🏆 Тейк забран! Ровно по плану.",
    "🔥 Красивая сделка, идём дальше.",
    "✅ Сработало! Система работает.",
]


def fmt_position(p: db.Position, with_result: bool = True) -> str:
    emoji = {"active": "⏳", "tp": "✅", "sl": "❌", "missed": "🚫", "cancelled": "🗑"}
    lines = [
        f"{emoji.get(p.status, '')} <b>{escape_html(p.ticker)}</b> ({escape_html(p.direction)})",
        f"ТВХ: <code>{p.entry}</code> | Стоп: <code>{p.stop_loss}</code> | "
        f"Тейк: <code>{p.take_profit}</code> | R/R: <code>{p.risk_reward}</code>",
    ]
    if p.comment_open:
        lines.append(f"💭 Почему открыл: {escape_html(p.comment_open)}")
    if with_result and p.status != "active":
        if p.comment_close:
            lines.append(f"📝 Комментарий по закрытию: {escape_html(p.comment_close)}")
        lines.append(f"Закрыта: {p.closed_at}")
    lines.append(f"Открыта: {p.created_at}")
    return "\n".join(lines)


# ---------------------------------------------------------------- /start ---
@router.message(CommandStart(), state="*")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Привет! Это твой <b>журнал трейдера</b>.\n\n"
        "Здесь ты фиксируешь каждую сделку: тикер, точку входа, стоп, тейк "
        "и причину входа. А когда сделка закрывается — результат и скрин PnL.\n\n"
        "Выбирай действие:",
        reply_markup=kb.main_menu_kb(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("Главное меню:", reply_markup=kb.main_menu_kb())
    await call.answer()


# --------------------------------------------------------- Новая позиция ---
@router.callback_query(F.data == "new_position")
async def cb_new_position(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewPosition.ticker)
    await call.message.edit_text(
        "Введи тикер (например, <b>BTCUSDT</b>):",
        parse_mode=ParseMode.HTML,
    )
    await call.answer()


@router.message(~F.text.startswith("/"), NewPosition.ticker)
async def np_ticker(message: Message, state: FSMContext) -> None:
    await state.update_data(ticker=message.text.strip())
    await state.set_state(NewPosition.direction)
    await message.answer("Направление позиции:", reply_markup=kb.direction_kb())


@router.callback_query(NewPosition.direction, F.data.startswith("dir:"))
async def np_direction(call: CallbackQuery, state: FSMContext) -> None:
    direction = call.data.split(":", 1)[1]
    await state.update_data(direction=direction)
    await state.set_state(NewPosition.entry)
    await call.message.edit_text("Укажи ТВХ (цену входа), число:")
    await call.answer()


def _parse_float(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


@router.message(~F.text.startswith("/"), NewPosition.entry)
async def np_entry(message: Message, state: FSMContext) -> None:
    value = _parse_float(message.text)
    if value is None:
        await message.answer("Это не похоже на число. Введи ТВХ ещё раз:")
        return
    await state.update_data(entry=value)
    await state.set_state(NewPosition.stop_loss)
    await message.answer("Укажи стоп-лосс:")


@router.message(~F.text.startswith("/"), NewPosition.stop_loss)
async def np_stop(message: Message, state: FSMContext) -> None:
    value = _parse_float(message.text)
    if value is None:
        await message.answer("Это не похоже на число. Введи стоп-лосс ещё раз:")
        return
    await state.update_data(stop_loss=value)
    await state.set_state(NewPosition.take_profit)
    await message.answer("Укажи тейк-профит:")


@router.message(~F.text.startswith("/"), NewPosition.take_profit)
async def np_take(message: Message, state: FSMContext) -> None:
    value = _parse_float(message.text)
    if value is None:
        await message.answer("Это не похоже на число. Введи тейк-профит ещё раз:")
        return
    await state.update_data(take_profit=value)
    await state.set_state(NewPosition.comment)
    await message.answer("Почему открываешь эту позицию? (коротко опиши идею)")


@router.message(~F.text.startswith("/"), NewPosition.comment)
async def np_comment(message: Message, state: FSMContext) -> None:
    data = await state.update_data(comment=message.text.strip())
    position_id = await db.add_position(
        DB_PATH,
        user_id=message.from_user.id,
        ticker=data["ticker"],
        direction=data["direction"],
        entry=data["entry"],
        stop_loss=data["stop_loss"],
        take_profit=data["take_profit"],
        comment_open=data["comment"],
    )
    await state.clear()
    position = await db.get_position(DB_PATH, position_id)
    await message.answer(
        "Позиция добавлена в активные ✅\n\n" + fmt_position(position, with_result=False),
        reply_markup=kb.back_to_menu_kb(),
        parse_mode=ParseMode.HTML,
    )


# ------------------------------------------------------ Активные позиции ---
@router.callback_query(F.data == "active_positions")
async def cb_active_positions(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    positions = await db.get_active_positions(DB_PATH, call.from_user.id)
    if not positions:
        await call.message.edit_text(
            "Активных позиций нет. Заведи новую через меню 👇",
            reply_markup=kb.main_menu_kb(),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()
        return
    await call.message.edit_text(f"Активных позиций: {len(positions)}")
    for p in positions:
        await call.message.answer(
            fmt_position(p, with_result=False),
            reply_markup=kb.active_position_kb(p.id),
            parse_mode=ParseMode.HTML,
        )
    await call.answer()


@router.callback_query(F.data.startswith("del:"))
async def cb_delete_ask(call: CallbackQuery) -> None:
    position_id = int(call.data.split(":", 1)[1])
    await call.message.answer(
        "Точно удалить эту позицию без сохранения в историю?",
        reply_markup=kb.confirm_delete_kb(position_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("delconfirm:"))
async def cb_delete_confirm(call: CallbackQuery) -> None:
    position_id = int(call.data.split(":", 1)[1])
    await db.delete_position(DB_PATH, position_id)
    await call.message.edit_text("Позиция удалена 🗑")
    await call.answer()


# --------------------------------------------------- Закрытие по тейку/стопу
@router.callback_query(F.data.startswith("tp:"))
async def cb_tp(call: CallbackQuery, state: FSMContext) -> None:
    position_id = int(call.data.split(":", 1)[1])
    await state.set_state(ClosePosition.waiting_photo)
    await state.update_data(position_id=position_id, result="tp")
    await call.message.answer("🎉 Отлично! Пришли скрин PnL по этой сделке:")
    await call.answer()


@router.callback_query(F.data.startswith("sl:"))
async def cb_sl(call: CallbackQuery, state: FSMContext) -> None:
    position_id = int(call.data.split(":", 1)[1])
    await state.set_state(ClosePosition.waiting_photo)
    await state.update_data(position_id=position_id, result="sl")
    await call.message.answer("Пришли скрин PnL по этой сделке:")
    await call.answer()


@router.message(ClosePosition.waiting_photo, F.photo)
async def cp_photo(message: Message, state: FSMContext) -> None:
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    data = await state.get_data()
    await state.set_state(ClosePosition.waiting_comment)
    if data["result"] == "tp":
        await message.answer(
            "Скрин сохранён. Добавь комментарий к сделке (или нажми «Пропустить» — "
            "подставлю победную фразу):",
            reply_markup=kb.skip_comment_kb(),
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "Скрин сохранён. Почему сделка не отработала и ушла в стоп? "
            "(что пошло не так, что учесть в следующий раз)",
            reply_markup=kb.skip_comment_kb(),
            parse_mode=ParseMode.HTML,
        )


@router.message(ClosePosition.waiting_photo, ~F.photo, ~F.text.startswith("/"))
async def cp_photo_wrong(message: Message) -> None:
    await message.answer("Нужен именно скрин (фото) с PnL. Пришли его картинкой 🖼")


async def _finalize_close(message_or_call, state: FSMContext, comment_text: str | None) -> None:
    data = await state.get_data()
    result = data["result"]
    if result == "tp" and not comment_text:
        comment_text = random.choice(VICTORY_PHRASES)
    await db.close_position(
        DB_PATH,
        position_id=data["position_id"],
        status=result,
        comment_close=comment_text,
        photo_file_id=data.get("photo_file_id"),
    )
    await state.clear()
    position = await db.get_position(DB_PATH, data["position_id"])
    caption = ("Сделка закрыта и добавлена в историю.\n\n" + fmt_position(position))
    target = message_or_call.message if isinstance(message_or_call, CallbackQuery) else message_or_call
    if position.photo_file_id:
        await target.answer_photo(position.photo_file_id, caption=caption, reply_markup=kb.back_to_menu_kb())
    else:
        await target.answer(caption, reply_markup=kb.back_to_menu_kb())


@router.message(ClosePosition.waiting_comment, ~F.text.startswith("/"))
async def cp_comment(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text == "-":
        text = None
    await _finalize_close(message, state, text)


@router.callback_query(ClosePosition.waiting_comment, F.data == "skip_comment")
async def cp_comment_skip(call: CallbackQuery, state: FSMContext) -> None:
    await _finalize_close(call, state, None)
    await call.answer()


# ------------------------------------------------------- Не дошло до ТВХ ---
@router.callback_query(F.data.startswith("missed:"))
async def cb_missed(call: CallbackQuery, state: FSMContext) -> None:
    position_id = int(call.data.split(":", 1)[1])
    await state.set_state(MissedPosition.waiting_comment)
    await state.update_data(position_id=position_id)
    await call.message.answer("Почему цена не дошла до ТВХ? (кратко опиши, что произошло)")
    await call.answer()


@router.message(MissedPosition.waiting_comment, ~F.text.startswith("/"))
async def missed_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db.close_position(
        DB_PATH,
        position_id=data["position_id"],
        status="missed",
        comment_close=message.text.strip(),
        photo_file_id=None,
    )
    await state.clear()
    position = await db.get_position(DB_PATH, data["position_id"])
    await message.answer(
        "Отметил как «не дошло до ТВХ», сохранил в историю.\n\n" + fmt_position(position),
        reply_markup=kb.back_to_menu_kb(),
        parse_mode=ParseMode.HTML,
    )


# ------------------------------------------------------------- История -----
@router.callback_query(F.data.startswith("history:"))
async def cb_history(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    offset = int(call.data.split(":", 1)[1])
    total = await db.count_history(DB_PATH, call.from_user.id)
    positions = await db.get_history(DB_PATH, call.from_user.id, limit=5, offset=offset)
    if not positions:
        await call.message.edit_text(
            "История пока пуста — закрытых сделок нет.", reply_markup=kb.main_menu_kb()
        )
        await call.answer()
        return
    text = f"📚 История (сделок всего: {total})\n\n" + "\n\n".join(
        fmt_position(p) for p in positions
    )
    has_more = offset + 5 < total
    await call.message.edit_text(
        text,
        reply_markup=kb.history_kb(offset, has_more),
        parse_mode=ParseMode.HTML,
    )
    await call.answer()


# ---------------------------------------------------------- Статистика ----
@router.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    s = await db.get_stats(DB_PATH, call.from_user.id)
    text = (
        "📈 <b>Статистика</b>\n\n"
        f"Активных позиций: {s['active']}\n"
        f"Закрыто по тейку: {s['tp']}\n"
        f"Закрыто по стопу: {s['sl']}\n"
        f"Не дошло до ТВХ: {s['missed']}\n\n"
        f"Всего завершённых сделок (тейк/стоп): {s['closed_trades']}\n"
        f"Винрейт: <b>{s['winrate']}%</b>"
    )
    await call.message.edit_text(
        text,
        reply_markup=kb.back_to_menu_kb(),
        parse_mode=ParseMode.HTML,
    )
    await call.answer()


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN. Скопируй .env.example в .env и впиши токен.")
    await db.init_db(DB_PATH)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

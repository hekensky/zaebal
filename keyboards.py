from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новая позиция", callback_data="new_position")
    kb.button(text="📊 Активные позиции", callback_data="active_positions")
    kb.button(text="📚 История", callback_data="history:0")
    kb.button(text="📈 Статистика", callback_data="stats")
    kb.adjust(1)
    return kb.as_markup()


def direction_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 LONG", callback_data="dir:LONG")
    kb.button(text="🔴 SHORT", callback_data="dir:SHORT")
    kb.adjust(2)
    return kb.as_markup()


def active_position_kb(position_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Закрылась по тейку", callback_data=f"tp:{position_id}")
    kb.button(text="❌ Закрылась по стопу", callback_data=f"sl:{position_id}")
    kb.button(text="⏳ Не дошло до ТВХ", callback_data=f"missed:{position_id}")
    kb.button(text="🗑 Удалить", callback_data=f"del:{position_id}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_kb(position_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, удалить", callback_data=f"delconfirm:{position_id}")
    kb.button(text="Отмена", callback_data="active_positions")
    kb.adjust(2)
    return kb.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu")
    return kb.as_markup()


def history_kb(offset: int, has_more: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    row = []
    if offset > 0:
        row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"history:{max(offset - 5, 0)}"))
    if has_more:
        row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"history:{offset + 5}"))
    if row:
        kb.row(*row)
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def skip_comment_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить", callback_data="skip_comment")
    return kb.as_markup()

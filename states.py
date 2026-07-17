from aiogram.fsm.state import State, StatesGroup


class NewPosition(StatesGroup):
    ticker = State()
    direction = State()
    entry = State()
    stop_loss = State()
    take_profit = State()
    comment = State()


class ClosePosition(StatesGroup):
    waiting_photo = State()
    waiting_comment = State()


class MissedPosition(StatesGroup):
    waiting_comment = State()

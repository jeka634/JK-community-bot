from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Setting
from sqlalchemy import select
import config

router = Router()

# Middleware для проверки, является ли пользователь администратором
@router.message.middleware()
@router.callback_query.middleware()
async def admin_check(handler, event, data):
    if str(event.from_user.id) != config.ADMIN_TELEGRAM_ID:
        # Игнорируем команды от не-администраторов
        return
    return await handler(event, data)

async def get_or_create_setting(session: AsyncSession, key: str, default_value: str = ''):
    result = await session.execute(select(Setting).filter_by(key=key))
    setting = result.scalar_one_or_none()
    if not setting:
        setting = Setting(key=key, value=default_value)
        session.add(setting)
        await session.commit()
    return setting

@router.message(Command("admin_add_word"))
async def add_word_handler(message: types.Message, session: AsyncSession):
    try:
        word = message.text.split(maxsplit=1)[1].strip().lower()
    except IndexError:
        await message.reply("Пожалуйста, укажите слово для добавления. Пример: `/admin_add_word [слово]`")
        return

    setting = await get_or_create_setting(session, 'forbidden_words')
    words = set(setting.value.split(',')) if setting.value else set()
    if word in words:
        await message.reply(f"Слово '{word}' уже в списке.")
        return

    words.add(word)
    setting.value = ','.join(filter(None, words))
    await session.commit()
    await message.reply(f"Слово '{word}' добавлено в черный список.")

@router.message(Command("admin_remove_word"))
async def remove_word_handler(message: types.Message, session: AsyncSession):
    try:
        word = message.text.split(maxsplit=1)[1].strip().lower()
    except IndexError:
        await message.reply("Пожалуйста, укажите слово для удаления. Пример: `/admin_remove_word [слово]`")
        return

    setting = await get_or_create_setting(session, 'forbidden_words')
    words = set(setting.value.split(',')) if setting.value else set()
    if word not in words:
        await message.reply(f"Слово '{word}' не найдено в списке.")
        return

    words.remove(word)
    setting.value = ','.join(filter(None, words))
    await session.commit()
    await message.reply(f"Слово '{word}' удалено из черного списка.")

@router.message(Command("admin_list_words"))
async def list_words_handler(message: types.Message, session: AsyncSession):
    setting = await get_or_create_setting(session, 'forbidden_words')
    words = sorted([w for w in setting.value.split(',') if w])
    if not words:
        await message.reply("Черный список пуст.")
    else:
        await message.reply("Запрещенные слова:\n- " + "\n- ".join(words))

@router.message(Command("admin_toggle_happy_hour"))
async def toggle_happy_hour_handler(message: types.Message, session: AsyncSession):
    config.HAPPY_HOUR = not config.HAPPY_HOUR
    status = 'включён' if config.HAPPY_HOUR else 'выключен'
    await message.reply(f'Счастливый час {status}! Комиссия на игры: {int(config.get_game_commission()*100)}%') 
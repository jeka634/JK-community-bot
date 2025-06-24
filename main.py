import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.models import Base, User, Balance, DailyLimit, Setting
import config
from datetime import datetime, timedelta
from bot.ton_client import get_nfts_by_owner, is_veteran, is_legendary
from aiogram import F, Router
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from admin import handlers as admin_handlers
import random
import httpx
from games.dice import create_game_db, get_active_game_by_user, Currency, generate_temp_wallet, get_ton_connect_link, check_payment, finish_game_db
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.deep_linking import create_start_link
from bot.ton_onchain import send_jetton, send_ton

DATABASE_URL = 'sqlite+aiosqlite:///./db/database.db'

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

bot = Bot(token=config.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

router = Router()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='💰 Баланс'), KeyboardButton(text='🎲 Игры')],
            [KeyboardButton(text='💸 Перевести'), KeyboardButton(text='🏆 NFT-статус')],
            [KeyboardButton(text='👥 Рефералы'), KeyboardButton(text='🔗 Кошелёк')],
            [KeyboardButton(text='📤 Вывод'), KeyboardButton(text='ℹ️ Помощь')],
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def start_handler(message: Message):
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(
            select(User).filter_by(telegram_id=str(message.from_user.id))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
            session.add(user)
            await session.flush()
            if user.id is not None:
                session.add(Balance(user_id=user.id, jk_balance=0))
                session.add(DailyLimit(user_id=user.id, date=datetime.utcnow(), earned_today=0))
            await session.commit()
    welcome = (
        '👋 <b>Добро пожаловать в Jekardos coin Community Bot!</b>\n\n'
        'Этот бот — центр сообщества $JK:\n'
        '• Получай $JK за активность в чате (осмысленные сообщения)\n'
        '• Играйте в кости и другие игры на $JK и TON\n'
        '• P2P-переводы $JK между пользователями\n'
        '• NFT-статусы и бонусы для владельцев\n'
        '• Реферальная система\n'
        '• Автоматический бан за нарушения и разбан за $JK\n\n'
        '<b>Доступные команды:</b>\n'
        '/start — показать это сообщение\n'
        '/balance — баланс\n'
        '/connect_wallet — подключить TON-кошелек через TON Connect\n'
        '/check_status — проверить свой NFT-статус и бонусы\n'
        '/send [amount] @username — перевести $JK другому пользователю\n'
        '/dice @username [amount] [currency] — игра в кости на $JK или TON\n'
        '/withdraw — вывести $JK с внутреннего баланса\n'
        '/unban — разбаниться за $JK (если вы забанены)\n'
    )
    await message.answer(welcome, reply_markup=get_main_menu())

@dp.message(Command('connect_wallet'))
async def connect_wallet_handler(message: Message):
    tg_id = message.from_user.id
    link = f'{TON_CONNECT_BACKEND}/connect?tg_id={tg_id}'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Я подключил кошелек', callback_data='wallet_connected')]
    ])
    await message.reply(f'Для подключения TON-кошелька перейдите по ссылке и подтвердите в приложении TON Space/TONkeeper:\n{link}', reply_markup=kb)

@dp.message(Command('check_status'))
async def check_status_handler(message: Message):
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(
            select(User).filter_by(telegram_id=str(message.from_user.id))
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await message.reply('Сначала используйте /start!')
            return
        if not user.ton_address:
            await message.reply('Пожалуйста, отправьте свой TON-адрес одной строкой в ответ на это сообщение.')
            return
        nfts = await get_nfts_by_owner(str(user.ton_address))
        veteran = is_veteran(nfts)
        legendary = is_legendary(nfts)
        setattr(user, "is_legendary", bool(legendary))
        setattr(user, "is_veteran", bool(veteran or legendary))
        if legendary:
            await message.reply('Поздравляем! У вас есть легендарный NFT из коллекции. Вам присвоен статус "Легендарный Бывалый"!')
        elif veteran:
            await message.reply('Поздравляем! У вас есть NFT из коллекции. Вам присвоен статус "Бывалый"!')
        else:
            await message.reply('У вас нет NFT из нужных коллекций. Статус "Бывалый" не присвоен.')
        await session.commit()

@dp.message(Command('dice'))
async def dice_game_handler(message: Message):
    if not message.text:
        await message.reply('Некорректное сообщение.')
        return
    args = message.text.split()
    if len(args) != 4:
        await message.reply('Используйте: /dice @opponent [amount] [currency], например: /dice @username 1000 TON')
        return
    _, opponent_username, amount_str, currency_str = args
    if not opponent_username.startswith('@'):
        await message.reply('Укажите оппонента через @username')
        return
    try:
        amount = int(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply('Ставка должна быть положительным числом.')
        return
    currency = currency_str.upper()
    if currency not in ('TON', '$JK'):
        await message.reply('Валюта должна быть TON или $JK.')
        return
    async with AsyncSessionLocal() as session:
        opponent_result = await session.execute(
            select(User).filter_by(username=opponent_username.lstrip('@'))
        )
        opponent = opponent_result.scalar_one_or_none()
        if not opponent:
            await message.reply('Пользователь не найден или не зарегистрирован в боте.')
            return
        if opponent.telegram_id == str(message.from_user.id):
            await message.reply('Вы не можете играть сами с собой!')
            return
        # Проверяем, нет ли уже активной игры
        active_game = await get_active_game_by_user(session, message.from_user.id)
        if active_game:
            await message.reply('У вас уже есть активная игра. Вы можете вернуться к ней или сбросить её командой /reset_game.')
            return
        opponent_active_game = await get_active_game_by_user(session, int(opponent.telegram_id))
        if opponent_active_game:
            await message.reply('У оппонента уже есть активная игра. Попросите его завершить или сбросить её командой /reset_game.')
            return
        # Создаём игру в БД
        game = await create_game_db(session, message.from_user.id, int(opponent.telegram_id), amount, Currency(currency))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Accept challenge', callback_data=f'accept_dice_{game.initiator_id}')]
        ])
        await message.reply(f'@{opponent_username.lstrip("@")}! You are challenged to a dice game for {amount} {currency}. To participate, click the button below.', reply_markup=kb)

@dp.message(Command('reset_game'))
async def reset_game_handler(message: Message):
    async with AsyncSessionLocal() as session:
        game = await get_active_game_by_user(session, message.from_user.id)
        if not game:
            await message.reply('У вас нет активной игры.')
            return
        await finish_game_db(session, game)
        await message.reply('Ваша активная игра была сброшена. Теперь вы можете создать новую игру.')

@dp.message()
async def message_handler(message: Message):
    # Не обрабатываем команды как обычные сообщения
    if message.text and message.text.startswith('/'):
        return
    if not message.from_user or not message.text:
        return
    text = message.text.strip()
    # Проверка: не менее 5 слов
    words = text.split()
    if len(words) < 5:
        return
    def is_meaningless(word):
        return len(word) > 4 and (len(set(word.lower())) / len(word)) > 0.6
    if all(is_meaningless(w) for w in words):
        return
    if random.random() > 0.1:
        return
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(
            select(User).options(selectinload(User.balance), selectinload(User.daily_limit)).filter_by(telegram_id=str(message.from_user.id))
        )
        user = user_result.scalar_one_or_none()
        if not user or user.banned:
            return
        daily = user.daily_limit
        now = datetime.utcnow()
        if not daily or daily.date.date() != now.date():
            if daily:
                daily.date = now
                daily.earned_today = 0
            else:
                daily = DailyLimit(user_id=user.id, date=now, earned_today=0)
                session.add(daily)
        if daily.earned_today >= config.DAILY_JK_LIMIT:
            return
        bonus = 1.0
        if user.is_legendary:
            bonus += config.BONUS_LEGENDARY
        elif user.is_veteran:
            bonus += config.BONUS_VETERAN
        to_add = int(500 * bonus)
        to_add = min(to_add, config.DAILY_JK_LIMIT - daily.earned_today)
        user.balance.jk_balance += to_add
        daily.earned_today += to_add
        await session.commit()
        await message.reply(f'Вам начислено {to_add} $JK за активность!')
        # Проверка бонуса за реферал
        if user.referred_by:
            from db.models import Referral
            ref_result = await session.execute(select(Referral).filter_by(invited_id=user.id))
            ref = ref_result.scalar_one_or_none()
            if ref and not ref.bonus_given and daily.earned_today >= 20000:
                inviter_result = await session.execute(select(User).filter_by(id=user.referred_by))
                inviter = inviter_result.scalar_one_or_none()
                if inviter:
                    inviter.balance.jk_balance += 15000
                    user.balance.jk_balance += 15000
                    ref.bonus_given = True
                    await message.reply('Вы и ваш пригласивший получили по 15 000 $JK за активность!')
                    await bot.send_message(inviter.telegram_id, f'Ваш приглашённый @{user.username} стал активным! Вам начислено 15 000 $JK.')
                await session.commit()

def get_user_by_telegram_id(session, telegram_id):
    return session.scalar(session.query(User).filter_by(telegram_id=str(telegram_id)))

@dp.message(F.reply_to_message, F.text.regexp(r'^[UQ][A-Za-z0-9_-]{47,63}$'))
async def save_ton_address(message: Message):
    # Сохраняем TON-адрес пользователя
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(
            select(User).filter_by(telegram_id=str(message.from_user.id))
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await message.reply('Сначала используйте /start!')
            return
        user.ton_address = message.text.strip()
        await session.commit()
        await message.reply('TON-адрес сохранён! Теперь используйте /check_status.')

async def get_forbidden_words(session: AsyncSession) -> set:
    result = await session.execute(select(Setting).filter_by(key='forbidden_words'))
    setting = result.scalar_one_or_none()
    if setting is None or not setting.value:
        return set()
    return set(setting.value.split(','))

@dp.message.outer_middleware()
async def check_message_middleware(handler, event: Message, data):
    if not event.text or not event.from_user:
        return await handler(event, data)

    session: AsyncSession = data['session']
    
    # Проверка, забанен ли пользователь
    user_result = await session.execute(
        select(User).filter_by(telegram_id=str(event.from_user.id))
    )
    user = user_result.scalar_one_or_none()

    if user and user.banned:
        try:
            await event.delete()
        except Exception:
            pass # Не удалось удалить сообщение, возможно, нет прав
        return

    # Проверка на запрещенные слова
    forbidden_words = await get_forbidden_words(session)
    if any(word in event.text.lower() for word in forbidden_words):
        try:
            await event.delete()
            # Бан пользователя
            await event.bot.ban_chat_member(chat_id=event.chat.id, user_id=event.from_user.id)
            
            if not user:
                user = User(telegram_id=str(event.from_user.id), username=event.from_user.username, banned=True)
                session.add(user)
            else:
                user.banned = True
            
            await session.commit()
            await event.answer(f"Пользователь @{event.from_user.username} забанен за использование запрещенных слов.")
            # Отправка инструкции по разбану в ЛС
            try:
                await bot.send_message(
                    event.from_user.id,
                    f"Вы были забанены за нарушение правил чата.\n\nДля разбана переведите 2 000 000 $JK на TON-кошелек администратора: <code>{config.ADMIN_TON_ADDRESS}</code> и напишите /unban после оплаты."
                )
            except Exception as e:
                print(f"Не удалось отправить ЛС забаненному: {e}")
        except Exception as e:
            print(f"Не удалось забанить пользователя или удалить сообщение: {e}")
        return

    return await handler(event, data)

async def session_middleware(handler, event, data):
    async with AsyncSessionLocal() as session:
        data['session'] = session
        return await handler(event, data)

async def check_jk_unban_payment(ton_address: str, user_tg_id: str) -> bool:
    # Проверяем входящие транзакции на адрес администратора через tonapi.io
    url = f'https://tonapi.io/v2/accounts/{config.ADMIN_TON_ADDRESS}/jettons/transfers'
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        for tx in data.get('transfers', []):
            if (
                tx.get('from_address') == ton_address and
                tx.get('jetton', {}).get('address') == config.JK_TOKEN_CONTRACT and
                int(tx.get('amount', 0)) >= 2_000_000
            ):
                return True
    return False

@dp.message(Command('unban'))
async def unban_handler(message: Message):
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(
            select(User).filter_by(telegram_id=str(message.from_user.id))
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.banned:
            await message.reply('Вы не забанены.')
            return
        if not user.ton_address:
            await message.reply('У вас не указан TON-адрес. Пожалуйста, отправьте его в ответ на это сообщение.')
            return
        await message.reply('Проверяю оплату...')
        paid = await check_jk_unban_payment(user.ton_address, user.telegram_id)
        if paid:
            user.banned = False
            await session.commit()
            await message.reply('Оплата получена! Вы разбанены и можете снова писать в чате.')
        else:
            await message.reply('Платёж не найден. Убедитесь, что вы перевели 2 000 000 $JK на правильный адрес и попробуйте снова через минуту.')

@dp.message(Command('send'))
async def send_jk_handler(message: Message):
    args = message.text.split()
    if len(args) != 3:
        await message.reply('Используйте: /send [количество] @username')
        return
    _, amount_str, recipient_username = args
    try:
        amount = int(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply('Сумма должна быть положительным числом.')
        return
    if not recipient_username.startswith('@'):
        await message.reply('Укажите получателя через @username')
        return
    async with AsyncSessionLocal() as session:
        sender_result = await session.execute(select(User).filter_by(telegram_id=str(message.from_user.id)))
        sender = sender_result.scalar_one_or_none()
        recipient_result = await session.execute(select(User).filter_by(username=recipient_username.lstrip('@')))
        recipient = recipient_result.scalar_one_or_none()
        if not sender or not sender.ton_address:
            await message.reply('У вас не указан TON-адрес. Используйте /check_status.')
            return
        if not recipient or not recipient.ton_address:
            await message.reply('У получателя не указан TON-адрес.')
            return
        if sender.telegram_id == recipient.telegram_id:
            await message.reply('Нельзя отправить $JK самому себе.')
            return
        # Генерируем TON Connect-ссылку для перевода $JK
        link = get_ton_connect_link(recipient.ton_address, amount, Currency.JK)
        await message.reply(
            f'Для перевода {amount} $JK пользователю @{recipient.username} перейдите по ссылке и подтвердите транзакцию:\n'
            f'{link}\n\n'
            f'После перевода напишите /confirm_send {amount} @{recipient.username}'
        )

@dp.message(Command('confirm_send'))
async def confirm_send_handler(message: Message):
    args = message.text.split()
    if len(args) != 3:
        await message.reply('Используйте: /confirm_send [количество] @username')
        return
    _, amount_str, recipient_username = args
    try:
        amount = int(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply('Сумма должна быть положительным числом.')
        return
    if not recipient_username.startswith('@'):
        await message.reply('Укажите получателя через @username')
        return
    async with AsyncSessionLocal() as session:
        sender_result = await session.execute(select(User).filter_by(telegram_id=str(message.from_user.id)))
        sender = sender_result.scalar_one_or_none()
        recipient_result = await session.execute(select(User).filter_by(username=recipient_username.lstrip('@')))
        recipient = recipient_result.scalar_one_or_none()
        if not sender or not sender.ton_address:
            await message.reply('У вас не указан TON-адрес. Используйте /check_status.')
            return
        if not recipient or not recipient.ton_address:
            await message.reply('У получателя не указан TON-адрес.')
            return
        from games.dice import check_payment
        paid = await check_payment(recipient.ton_address, sender.ton_address, amount, Currency.JK)
        if paid:
            await message.reply(f'Перевод {amount} $JK пользователю @{recipient.username} подтверждён!')
            await bot.send_message(recipient.telegram_id, f'Вам поступил перевод {amount} $JK от пользователя @{sender.username}!')
        else:
            await message.reply('Перевод не найден. Убедитесь, что вы отправили $JK на TON-адрес получателя и попробуйте снова через минуту.')

# --- FSM для перевода $JK ---
class SendJKState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_username = State()

# --- FSM для вывода $JK ---
class WithdrawJKState(StatesGroup):
    waiting_for_amount = State()

# --- Вложенное меню для игр ---
def get_games_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='🎲 Кости')],
            [KeyboardButton(text='⬅️ Назад')]
        ], resize_keyboard=True
    )

# --- Вложенное меню для перевода ---
def get_send_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='💸 Перевести $JK')],
            [KeyboardButton(text='⬅️ Назад')]
        ], resize_keyboard=True
    )

# --- Обработчик главного меню ---
@dp.message(lambda m: m.text in ['💰 Баланс', '🎲 Игры', '💸 Перевести', '🏆 NFT-статус', '👥 Рефералы', '🔗 Кошелёк', '📤 Вывод', 'ℹ️ Помощь'])
async def main_menu_handler(message: Message, state: FSMContext):
    if message.text == '💰 Баланс':
        await balance_handler(message, show_menu=True)
    elif message.text == '🎲 Игры':
        await message.answer('Выберите игру:', reply_markup=get_games_menu())
    elif message.text == '💸 Перевести':
        await message.answer('Выберите тип перевода:', reply_markup=get_send_menu())
    elif message.text == '🏆 NFT-статус':
        await check_status_menu(message)
    elif message.text == '👥 Рефералы':
        await referral_menu(message)
    elif message.text == '🔗 Кошелёк':
        await connect_wallet_menu(message)
    elif message.text == '📤 Вывод':
        await message.answer('Введите сумму для вывода $JK:', reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='⬅️ Назад')]], resize_keyboard=True))
        await state.set_state(WithdrawJKState.waiting_for_amount)
    elif message.text == 'ℹ️ Помощь':
        await message.answer('Справка по боту:\n/start — описание и команды\nВопросы: @JKcoin_support', reply_markup=get_main_menu())
    elif message.text == '⬅️ Назад':
        await message.answer('Главное меню:', reply_markup=get_main_menu())

# --- Обработка вложенного меню игр ---
@dp.message(lambda m: m.text == '🎲 Кости')
async def dice_menu_handler(message: Message):
    await message.answer('Для игры в кости используйте команду:\n/dice @username [amount] [currency]\n(Скоро: запуск через кнопки)', reply_markup=get_main_menu())

# --- Обработка вложенного меню перевода ---
@dp.message(lambda m: m.text == '💸 Перевести $JK')
async def send_jk_start(message: Message, state: FSMContext):
    await message.answer('Введите сумму для перевода $JK:', reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='⬅️ Назад')]], resize_keyboard=True))
    await state.set_state(SendJKState.waiting_for_amount)

# --- FSM шаги для перевода $JK ---
@dp.message(SendJKState.waiting_for_amount)
async def send_jk_amount(message: Message, state: FSMContext):
    if message.text == '⬅️ Назад':
        await message.answer('Главное меню:', reply_markup=get_main_menu())
        await state.clear()
        return
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply('Введите корректную сумму для перевода.')
        return
    await state.update_data(amount=amount)
    await message.answer('Введите @username получателя:', reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='⬅️ Назад')]], resize_keyboard=True))
    await state.set_state(SendJKState.waiting_for_username)

@dp.message(SendJKState.waiting_for_username)
async def send_jk_username(message: Message, state: FSMContext):
    if message.text == '⬅️ Назад':
        await message.answer('Главное меню:', reply_markup=get_main_menu())
        await state.clear()
        return
    username = message.text.strip().lstrip('@')
    data = await state.get_data()
    amount = data.get('amount')
    if not username:
        await message.reply('Введите корректный username.')
        return
    async with AsyncSessionLocal() as session:
        sender_result = await session.execute(select(User).filter_by(telegram_id=str(message.from_user.id)))
        sender = sender_result.scalar_one_or_none()
        recipient_result = await session.execute(select(User).filter_by(username=username))
        recipient = recipient_result.scalar_one_or_none()
        if not sender or not sender.ton_address:
            await message.reply('У вас не указан TON-адрес. Используйте /check_status.', reply_markup=get_main_menu())
            await state.clear()
            return
        if not recipient or not recipient.ton_address:
            await message.reply('У получателя не указан TON-адрес.', reply_markup=get_main_menu())
            await state.clear()
            return
        if sender.telegram_id == recipient.telegram_id:
            await message.reply('Нельзя отправить $JK самому себе.', reply_markup=get_main_menu())
            await state.clear()
            return
        link = get_ton_connect_link(recipient.ton_address, amount, Currency.JK)
        await message.reply(
            f'Для перевода {amount} $JK пользователю @{recipient.username} перейдите по ссылке и подтвердите транзакцию:\n'
            f'{link}\n\n'
            f'После перевода напишите /confirm_send {amount} @{recipient.username}',
            reply_markup=get_main_menu()
        )
        await state.clear()

# --- FSM шаги для вывода $JK ---
@dp.message(WithdrawJKState.waiting_for_amount)
async def withdraw_jk_amount(message: Message, state: FSMContext):
    if message.text == '⬅️ Назад':
        await message.answer('Главное меню:', reply_markup=get_main_menu())
        await state.clear()
        return
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply('Введите корректную сумму для вывода.')
        return
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(select(User).options(selectinload(User.balance)).filter_by(telegram_id=str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user or not user.balance:
            await message.reply('Пользователь не найден или баланс не инициализирован.', reply_markup=get_main_menu())
            await state.clear()
            return
        if amount > user.balance.jk_balance:
            await message.reply('Недостаточно средств на балансе.', reply_markup=get_main_menu())
            await state.clear()
            return
        is_veteran = user.is_veteran or user.is_legendary
        from config import get_game_commission, JEKARDOS_BANK_ADDRESS
        commission = 0.0 if is_veteran else get_game_commission()
        commission_amount = int(amount * commission)
        to_receive = amount - commission_amount
        link = get_ton_connect_link(user.ton_address, to_receive, Currency.JK)
        await message.reply(
            f'К выводу: {amount} $JK\nКомиссия бота: {commission_amount} $JK\nИтого к получению: {to_receive} $JK\n\nДля получения средств подтвердите вывод по ссылке (TON Connect):\n{link}\n\nПосле получения средств напишите /confirm_withdraw {amount}',
            reply_markup=get_main_menu()
        )
        await state.clear()

@dp.message(Command('referral'))
async def referral_handler(message: Message):
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(select(User).filter_by(telegram_id=str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.reply('Сначала используйте /start!')
            return
        ref_link = f'https://t.me/{(await bot.me()).username}?start=ref_{user.id}'
        await message.reply(
            f'Ваша реферальная ссылка:\n'
            f'{ref_link}\n\n'
            f'Приглашайте друзей и получайте бонусы!'
        )

@dp.message(CommandStart(deep_link=True))
async def start_deep_link_handler(message: Message, command: CommandStart):
    payload = command.args
    if payload and payload.startswith('ref_'):
        inviter_id = int(payload[4:])
        async with AsyncSessionLocal() as session:
            user_result = await session.execute(select(User).filter_by(telegram_id=str(message.from_user.id)))
            user = user_result.scalar_one_or_none()
            if not user:
                user = User(telegram_id=str(message.from_user.id), username=message.from_user.username)
                session.add(user)
                await session.flush()
                if user.id is not None:
                    session.add(Balance(user_id=user.id, jk_balance=0))
                    session.add(DailyLimit(user_id=user.id, date=datetime.utcnow(), earned_today=0))
            # Проверяем, не был ли уже установлен реферал
            if user and not user.referred_by and user.id != inviter_id:
                user.referred_by = inviter_id
                from db.models import Referral
                session.add(Referral(inviter_id=inviter_id, invited_id=user.id, bonus_given=False))
            await session.commit()
        await message.answer('Добро пожаловать по реферальной ссылке!')
    else:
        await start_handler(message)

TON_CONNECT_BACKEND = 'http://localhost:8080'  # Замените на ваш внешний адрес при деплое

@dp.callback_query(lambda c: c.data == 'wallet_connected')
async def wallet_connected_callback(callback: CallbackQuery):
    tg_id = callback.from_user.id
    url = f'{TON_CONNECT_BACKEND}/get_address?session_id={tg_id}'
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        try:
            data = resp.json()
            address = data.get('address')
        except Exception:
            await callback.message.answer('Ошибка при получении адреса из TON Connect. Попробуйте ещё раз позже.')
            return
    if address:
        async with AsyncSessionLocal() as session:
            user_result = await session.execute(select(User).filter_by(telegram_id=str(tg_id)))
            user = user_result.scalar_one_or_none()
            if user:
                user.ton_address = address
                await session.commit()
                await callback.message.answer(f'Ваш TON-адрес успешно подключён: {address}')
            else:
                await callback.message.answer('Сначала используйте /start!')
    else:
        await callback.message.answer('Кошелек не найден. Попробуйте ещё раз после подключения через ссылку.')

@dp.callback_query(lambda c: c.data.startswith('accept_dice_'))
async def accept_dice_callback(callback: CallbackQuery):
    initiator_id = int(callback.data.split('_')[-1])
    async with AsyncSessionLocal() as session:
        game = await get_active_game_by_user(session, callback.from_user.id)
        if not game or game.initiator_id != initiator_id or game.opponent_id != callback.from_user.id:
            await callback.answer('Игра не найдена или вы не приглашены.', show_alert=True)
            return
        if game.accepted:
            await callback.answer('Игра уже принята.', show_alert=True)
            return
        game.accepted = True
        await session.commit()
        temp_wallet = generate_temp_wallet()
        game.temp_wallet = temp_wallet
        await session.commit()
        initiator_result = await session.execute(select(User).filter_by(telegram_id=str(game.initiator_id)))
        initiator = initiator_result.scalar_one_or_none()
        opponent_result = await session.execute(select(User).filter_by(telegram_id=str(game.opponent_id)))
        opponent = opponent_result.scalar_one_or_none()
        if not initiator or not opponent or not initiator.ton_address or not opponent.ton_address:
            await callback.message.edit_text('Оба игрока должны указать свой TON-адрес через /check_status.')
            return
        link1 = get_ton_connect_link(temp_wallet, game.amount, Currency(game.currency))
        link2 = get_ton_connect_link(temp_wallet, game.amount, Currency(game.currency))
        await bot.send_message(game.initiator_id, f'Переведите {game.amount} {game.currency} для участия в игре: {link1}')
        await bot.send_message(game.opponent_id, f'Переведите {game.amount} {game.currency} для участия в игре: {link2}')
        await callback.message.edit_text('Ожидаем поступления ставок от обоих игроков. После оплаты бот автоматически определит победителя.')
        for _ in range(30):
            paid1 = await check_payment(temp_wallet, initiator.ton_address, game.amount, Currency(game.currency))
            paid2 = await check_payment(temp_wallet, opponent.ton_address, game.amount, Currency(game.currency))
            if paid1:
                game.initiator_paid = True
            if paid2:
                game.opponent_paid = True
            await session.commit()
            if game.initiator_paid and game.opponent_paid:
                break
            await asyncio.sleep(2)
        if not (game.initiator_paid and game.opponent_paid):
            await bot.send_message(game.initiator_id, 'Не все ставки поступили вовремя. Игра отменена.')
            await bot.send_message(game.opponent_id, 'Не все ставки поступили вовремя. Игра отменена.')
            game.finished = True
            await session.commit()
            return
        import random
        winner_id = random.choice([game.initiator_id, game.opponent_id])
        game.winner_id = winner_id
        game.finished = True
        await session.commit()
        # Комиссия
        winner = initiator if winner_id == game.initiator_id else opponent
        is_veteran = winner.is_veteran or winner.is_legendary
        from config import get_game_commission, ADMIN_TON_ADDRESS, JK_TOKEN_CONTRACT
        commission = 0.0 if is_veteran else get_game_commission()
        total_bank = game.amount * 2
        commission_amount = int(total_bank * commission)
        win_amount = total_bank - commission_amount
        # On-chain выплата выигрыша
        try:
            if game.currency == 'TON':
                tx_hash = await send_ton(winner.ton_address, win_amount / 1e9, comment='Выигрыш в игре Dice')
                if commission_amount > 0:
                    await send_ton(ADMIN_TON_ADDRESS, commission_amount / 1e9, comment='Комиссия за игру Dice')
            else:
                tx_hash = await send_jetton(winner.ton_address, JK_TOKEN_CONTRACT, win_amount, comment='Выигрыш в игре Dice')
                if commission_amount > 0:
                    await send_jetton(ADMIN_TON_ADDRESS, JK_TOKEN_CONTRACT, commission_amount, comment='Комиссия за игру Dice')
            await bot.send_message(winner_id, f'Поздравляем! Вы выиграли {win_amount} {game.currency}. Tx: {tx_hash}')
        except Exception as e:
            await bot.send_message(winner_id, f'Ошибка при отправке выигрыша: {e}')
        await bot.send_message(game.initiator_id if winner_id != game.initiator_id else game.opponent_id, f'Игра завершена! Победитель: @{winner.username}')

@dp.message(Command('balance'))
async def balance_handler(message: Message, show_menu: bool = False):
    async with AsyncSessionLocal() as session:
        user_result = await session.execute(select(User).options(selectinload(User.balance)).filter_by(telegram_id=str(message.from_user.id)))
        user = user_result.scalar_one_or_none()
        if not user or not user.balance:
            await message.reply('Пользователь не найден или баланс не инициализирован.', reply_markup=get_main_menu() if show_menu else None)
            return
        username = user.username or f"id{user.telegram_id}"
        jk_balance = user.balance.jk_balance
        await message.reply(f'{username} : {jk_balance} $JK', reply_markup=get_main_menu() if show_menu else None)

# Обработчик кнопок главного меню
@dp.message(lambda m: m.text in ['💰 Баланс', '🎲 Игры', '💸 Перевести', '🏆 NFT-статус', '👥 Рефералы', '🔗 Кошелёк', '📤 Вывод', 'ℹ️ Помощь'])
async def main_menu_handler(message: Message):
    if message.text == '💰 Баланс':
        await balance_handler(message, show_menu=True)
    elif message.text == '🎲 Игры':
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='🎲 Кости'), KeyboardButton(text='🪨✂️📄 Скоро!')],
                [KeyboardButton(text='⬅️ Назад')]
            ], resize_keyboard=True
        )
        await message.answer('Выберите игру:', reply_markup=kb)
    elif message.text == '💸 Перевести':
        await message.answer('Для перевода $JK используйте команду:\n/send [количество] @username', reply_markup=get_main_menu())
    elif message.text == '🏆 NFT-статус':
        await check_status_menu(message)
    elif message.text == '👥 Рефералы':
        await referral_menu(message)
    elif message.text == '🔗 Кошелёк':
        await connect_wallet_menu(message)
    elif message.text == '📤 Вывод':
        await withdraw_menu(message)
    elif message.text == 'ℹ️ Помощь':
        await message.answer('Справка по боту:\n/start — описание и команды\nВопросы: @JKcoin_support', reply_markup=get_main_menu())
    elif message.text == '⬅️ Назад':
        await message.answer('Главное меню:', reply_markup=get_main_menu())

# Обертки для вызова команд с reply_markup из меню
async def check_status_menu(message: Message):
    await check_status_handler(message)
    await message.answer('Главное меню:', reply_markup=get_main_menu())

async def referral_menu(message: Message):
    await referral_handler(message)
    await message.answer('Главное меню:', reply_markup=get_main_menu())

async def connect_wallet_menu(message: Message):
    await connect_wallet_handler(message)
    await message.answer('Главное меню:', reply_markup=get_main_menu())

async def withdraw_menu(message: Message):
    await message.answer('Для вывода используйте команду:\n/withdraw', reply_markup=get_main_menu())

async def main():
    await init_db()
    
    # Регистрируем middleware
    dp.update.outer_middleware.register(session_middleware)
    # Регистрируем роутеры
    dp.include_router(admin_handlers.router)

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main()) 
import asyncio
from enum import Enum
from typing import Optional, Dict
import config
import secrets
from db.models import DiceGameDB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

class Currency(str, Enum):
    JK = '$JK'
    TON = 'TON'

class DiceGame:
    def __init__(self, initiator_id: int, opponent_id: int, amount: int, currency: Currency):
        self.initiator_id = initiator_id
        self.opponent_id = opponent_id
        self.amount = amount
        self.currency = currency
        self.accepted = False
        self.initiator_paid = False
        self.opponent_paid = False
        self.winner_id: Optional[int] = None
        self.finished = False
        self.created_at = asyncio.get_event_loop().time()

# Хранилище активных игр (in-memory, можно заменить на БД)
active_games: Dict[int, DiceGame] = {}  # key: initiator_id

def create_game(initiator_id: int, opponent_id: int, amount: int, currency: Currency) -> DiceGame:
    game = DiceGame(initiator_id, opponent_id, amount, currency)
    active_games[initiator_id] = game
    return game

def get_game_by_user(user_id: int) -> Optional[DiceGame]:
    for game in active_games.values():
        if user_id in (game.initiator_id, game.opponent_id) and not game.finished:
            return game
    return None

def finish_game(game: DiceGame):
    game.finished = True
    if game.initiator_id in active_games:
        del active_games[game.initiator_id]

def generate_temp_wallet() -> str:
    # В реальном проекте — создать временный кошелек, здесь просто случайная строка
    return 'EQ' + secrets.token_urlsafe(32)[:48]

def get_ton_connect_link(address: str, amount: int, currency: Currency) -> str:
    if currency == Currency.TON:
        # TON Connect для TON
        return f'https://tonkeeper.com/transfer/{address}?amount={amount * 10**9}'
    else:
        # TON Connect для Jetton ($JK)
        return f'https://app.tonkeeper.com/transfer/{config.JK_TOKEN_CONTRACT}?recipient={address}&amount={amount}'

async def check_payment(address: str, user_ton_address: str, amount: int, currency: Currency) -> bool:
    import httpx
    if currency == Currency.TON:
        url = f'https://tonapi.io/v2/accounts/{address}/transactions?limit=20'
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            for tx in data.get('transactions', []):
                if tx.get('in_msg', {}).get('source') == user_ton_address and int(tx.get('in_msg', {}).get('value', 0)) >= amount * 10**9:
                    return True
    else:
        url = f'https://tonapi.io/v2/accounts/{address}/jettons/transfers'
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            for tx in data.get('transfers', []):
                if (
                    tx.get('from_address') == user_ton_address and
                    tx.get('jetton', {}).get('address') == config.JK_TOKEN_CONTRACT and
                    int(tx.get('amount', 0)) >= amount
                ):
                    return True
    return False

async def create_game_db(session: AsyncSession, initiator_id: int, opponent_id: int, amount: int, currency: Currency) -> DiceGameDB:
    game = DiceGameDB(
        initiator_id=initiator_id,
        opponent_id=opponent_id,
        amount=amount,
        currency=currency.value,
        accepted=False,
        initiator_paid=False,
        opponent_paid=False,
        finished=False
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)
    return game

async def get_active_game_by_user(session: AsyncSession, user_id: int) -> DiceGameDB:
    result = await session.execute(
        select(DiceGameDB).where(
            ((DiceGameDB.initiator_id == user_id) | (DiceGameDB.opponent_id == user_id)) & (DiceGameDB.finished == False)
        )
    )
    return result.scalar_one_or_none()

async def finish_game_db(session: AsyncSession, game: DiceGameDB):
    game.finished = True
    await session.commit() 
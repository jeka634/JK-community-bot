import os

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7777240436:AAGhj5OOq22nV0uNaW4iSAQdgyBB4qVf-QQ')
JEKARDOS_BANK_ADDRESS = os.getenv('JEKARDOS_BANK_ADDRESS', 'UQDfr9Y67dKlfdl-am3q4rxdcqfad7RfgIjOrWJSvLW8ytU-')
ADMIN_TON_ADDRESS = os.getenv('ADMIN_TON_ADDRESS', 'UQBuOVsMGzrwfWh8QH9tCu_VlJ_J-nSYtQXPIuMkb7bStG3A')
GETGEMS_ACCOUNT = os.getenv('GETGEMS_ACCOUNT', 'EQBuOVsMGzrwfWh8QH9tCu_VlJ_J-nSYtQXPIuMkb7bStDAF')
JK_TOKEN_CONTRACT = os.getenv('JK_TOKEN_CONTRACT', 'EQCktaxD_raMP6IARzMUL2XY-2hoe9N59xl11L6D8UOkqBI7')

# Лимиты и бонусы
JK_PER_MESSAGE = int(os.getenv('JK_PER_MESSAGE', 1000))
DAILY_JK_LIMIT = int(os.getenv('DAILY_JK_LIMIT', 40000))
BONUS_VETERAN = float(os.getenv('BONUS_VETERAN', 0.10))  # 10%
BONUS_LEGENDARY = float(os.getenv('BONUS_LEGENDARY', 0.12))  # 12%
UNBAN_COST = int(os.getenv('UNBAN_COST', 2000000))

# NFT-коллекции для "Бывалых"
NFT_COLLECTIONS = [
    'EQBAHcbCJWuZvluNFVWA3estS_O_53Viic_y4BukGHQe1-27',
    'EQBASsGE15DFJT3uKbJm9FQ54x7rMn0vzvyddINnIWqhaER2',
    'EQCSuo52ZNRstHgk-zPsAYqgJWV3FXvdAX6qYM3_6Bi2PtIh',
]

ADMIN_TELEGRAM_ID = os.getenv('648804551') # !!! ЗАМЕНИТЕ НА ВАШ TELEGRAM ID 

HAPPY_HOUR = False  # Флаг счастливого часа
GAME_COMMISSION = 0.05  # 5% стандартная комиссия
HAPPY_HOUR_COMMISSION = 0.02  # 2% во время happy hour

JK_BANK_MNEMONIC = os.getenv('JK_BANK_MNEMONIC', 'about useless snow egg glass begin inhale oval dress parade avoid topple alcohol aunt dune riot coconut music pair end before crack lizard chalk')

def get_game_commission():
    return HAPPY_HOUR_COMMISSION if HAPPY_HOUR else GAME_COMMISSION 
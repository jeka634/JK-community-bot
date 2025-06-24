from pytoniq import LiteBalancer, WalletV4R2, Address, begin_cell
import config
import asyncio

mnemonics = config.JK_BANK_MNEMONIC.split()

async def get_wallet_and_provider():
    provider = LiteBalancer.from_mainnet_config(1)
    await provider.start_up()
    wallet = await WalletV4R2.from_mnemonic(provider=provider, mnemonics=mnemonics)
    return wallet, provider

async def send_ton(to_address: str, amount_ton: float, comment: str = '') -> str:
    wallet, provider = await get_wallet_and_provider()
    # amount_ton в TON, переводим в nanotons
    amount = int(amount_ton * 1e9)
    body = None
    if comment:
        body = (begin_cell()
                .store_uint(0, 32)  # TextComment op-code
                .store_snake_string(comment)
                .end_cell())
    tx = await wallet.transfer(destination=to_address, amount=amount, body=body)
    await provider.close_all()
    return tx.hash.hex()

async def send_jetton(to_address: str, jetton_address: str, amount: int, comment: str = '') -> str:
    wallet, provider = await get_wallet_and_provider()
    # amount — в минимальных единицах (например, 1000000 для 1 $JK, если 6 знаков)
    # Получаем jetton wallet адрес для нашего кошелька
    jetton_wallet = await wallet.get_jetton_wallet(jetton_address)
    # Формируем payload для комментария
    forward_payload = None
    if comment:
        forward_payload = (begin_cell()
                           .store_uint(0, 32)
                           .store_snake_string(comment)
                           .end_cell())
    # Отправляем jetton
    tx = await wallet.jetton_transfer(
        jetton_wallet=jetton_wallet,
        destination=to_address,
        amount=amount,
        forward_amount=1000000,  # 0.001 TON на комиссию (можно изменить)
        forward_payload=forward_payload
    )
    await provider.close_all()
    return tx.hash.hex() 
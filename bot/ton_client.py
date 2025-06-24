import httpx
import config

TONAPI_BASE = 'https://tonapi.io/v2'

async def get_nfts_by_owner(address: str) -> list:
    url = f'{TONAPI_BASE}/accounts/{address}/nfts'
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get('nft_items', [])

def is_veteran(nfts: list) -> bool:
    for nft in nfts:
        if nft.get('collection', {}).get('address') in config.NFT_COLLECTIONS:
            return True
    return False

def is_legendary(nfts: list) -> bool:
    for nft in nfts:
        if nft.get('collection', {}).get('address') in config.NFT_COLLECTIONS:
            # Проверяем атрибуты NFT
            attributes = nft.get('metadata', {}).get('attributes', [])
            for attr in attributes:
                if attr.get('trait_type', '').lower() == 'type' and attr.get('value', '').lower() == 'легендарный':
                    return True
    return False 
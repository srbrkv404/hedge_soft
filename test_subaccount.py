"""
Тест торговли через SUB-ACCOUNT
"""

import os
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from dotenv import load_dotenv


load_dotenv()

MAIN_ADDRESS = os.getenv("MAIN_ADDRESS")
SUB_PRIVATE_KEY = os.getenv("SUB_PRIVATE_KEY")


def check_info(info_user, acc_address):
    main_checksum = Web3.to_checksum_address(acc_address)
    main_state = info_user.user_state(main_checksum)

    balance = main_state['marginSummary']['accountValue']
    # print(f"\n Баланс кошелька: ${balance}")

    # Проверяем позиции
    # positions = main_state.get('assetPositions', [])
    # if positions:
    #     print(f"\n Позиции на кошельке:")
    #     for asset_pos in positions:
    #         pos = asset_pos['position']
    #         if float(pos['szi']) != 0:
    #             print(f"  {pos['coin']}: {pos['szi']} @ ${pos['entryPx']}")
    # else:
    #     print("\n Нет открытых позиций")
    # print("\n" + "=" * 70)
    print(main_state)


def setup():
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    account: LocalAccount = Account.from_key(SUB_PRIVATE_KEY)

    exchange = Exchange(
        account,
        constants.MAINNET_API_URL,
        account_address=MAIN_ADDRESS
    )

    exchange.update_leverage(1, "ETH", False)

    return info, exchange

def increase_short(info, exchange):
    all_mids = info.all_mids()
    eth_price = float(all_mids.get("ETH", 0))

    limit_price = round(eth_price * 0.99, 1)
    
    min_size_eth = 10.0 / eth_price
    size_eth = max(0.003, min_size_eth)

    try:
        order_result = exchange.order(
            name="ETH",
            is_buy=False,
            sz=size_eth,
            limit_px=limit_price,
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=False
        )
        
        if order_result.get("ok"):
            print(f"ok")
        elif order_result.get("status") == "ok":
            print(f"status")
        print(f"   Result: {order_result}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def decrease_short(info, exchange):
    all_mids = info.all_mids()
    eth_price = float(all_mids.get("ETH", 0))

    limit_price = round(eth_price * 1.01, 1)
    
    min_size_eth = 10.0 / eth_price
    size_eth = max(0.003, min_size_eth)
    
    try:
        order_result = exchange.order(
            name="ETH",
            is_buy=True,
            sz=size_eth,
            limit_px=limit_price,
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=True
        )

        print(f"✅ Short decreased!")
        print(f"   Result: {order_result}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("1 - increase short")
    print("2 - decrease short")
    print("3 - exit")
    while True:
        x = int(input())
        if x == 1:
            info, exchange = setup()
            increase_short(info, exchange)
        elif x == 2:
            info, exchange = setup()
            decrease_short(info, exchange)
        elif x == 3:
            info, exchange = setup()
            check_info(info, MAIN_ADDRESS)
        else:
            break
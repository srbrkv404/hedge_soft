"""
Hyperliquid API Client для управления позициями
"""

import time
import json
import math
import os
from ekubo_config import *
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()


class HyperliquidClient:
    
    def __init__(self):
        self.main_address = os.getenv("MAIN_ADDRESS")
        self.base_url = constants.MAINNET_API_URL
        self.private_key = os.getenv("SUB_PRIVATE_KEY")
        self.account: LocalAccount = Account.from_key(self.private_key)
        self.exchange = Exchange(
            self.account,
            self.base_url,
            account_address=self.main_address
        )
        self.info = Info(self.base_url, skip_ws=True)

        self.deviation = 0.5
        self.timeout = 60

        self.control_loop_flag = True

        self.cur_eth_size = 0

        success, data = self.get_ekubo_positions()
        if success:
            self.cur_eth_size = data[0]
        else:
            self.cur_eth_size = 0
            print(f"❌ Init error: {data}")

    def set_deviation(self, deviation: float):
        self.deviation = deviation

    def set_timeout(self, timeout: int):
        self.timeout = timeout

    def get_deviation(self) -> float:
        return self.deviation

    def get_timeout(self) -> int:
        return self.timeout

    def get_eth_price(self) -> float:
        all_mids = self.info.all_mids()
        eth_price = float(all_mids.get("ETH", 0))
        return eth_price

    def increase_short(self):
        success, data = self.get_ekubo_positions()
        eth_price = self.get_eth_price()

        limit_price = round(eth_price * 0.99, 1)
        
        ekubo_eth_size = 0
        if success:
            ekubo_eth_size = data[0]
        
        increase_coef = (ekubo_eth_size - self.cur_eth_size) // self.deviation

        size_eth = max(
            math.ceil((10 / eth_price) * 1000) / 1000,
            round(self.deviation * increase_coef, 3)
        )

        try:
            order_result = self.exchange.order(
                name="ETH",
                is_buy=False,
                sz=size_eth,
                limit_px=limit_price,
                order_type={"limit": {"tif": "Ioc"}},
                reduce_only=False
            )

            if order_result.get("status") == "ok":
                return True, order_result
            else:
                return False, order_result
        except Exception as e:
            return False, str(e)

    def decrease_short(self):
        success, data = self.get_ekubo_positions()
        eth_price = self.get_eth_price()

        limit_price = round(eth_price * 1.01, 1)

        ekubo_eth_size = 0
        if success:
            ekubo_eth_size = data[0]
        
        decrease_coef = (ekubo_eth_size - self.cur_eth_size) // self.deviation
        
        size_eth = max(
            math.ceil((10 / eth_price) * 1000) / 1000,
            round(self.deviation * decrease_coef, 3)
        )
        
        try:
            order_result = self.exchange.order(
                name="ETH",
                is_buy=True,
                sz=size_eth,
                limit_px=limit_price,
                order_type={"limit": {"tif": "Ioc"}},
                reduce_only=True
            )

            if order_result.get("status") == "ok":
                return True, order_result
            else:
                return False, order_result
        except Exception as e:
            return False, str(e)

    def place_min_short(self):
        position = self.get_hl_positions()
        eth_price = self.get_eth_price()

        if position:
            current_size = float(position['szi'])
            size_eth = max(math.ceil((10 / eth_price) * 1000) / 1000, round(abs(current_size) - 0.001, 3))

            limit_price = round(eth_price * 1.01, 1)

            try:
                order_result = self.exchange.order(
                    name="ETH",
                    is_buy=True,
                    sz=size_eth,
                    limit_px=limit_price,
                    order_type={"limit": {"tif": "Ioc"}},
                    reduce_only=True
                )

                if order_result.get("status") == "ok":
                    return True, order_result
                else:
                    return False, order_result
            except Exception as e:
                return False, str(e)

    def place_max_short(self):
        position = self.get_hl_positions()
        eth_price = self.get_eth_price()
        ekubo_eth_size = 0
        success, data = self.get_ekubo_positions()
        if success:
            ekubo_eth_size = data[0]

        if position:
            current_size = float(position['szi'])
            size_eth = max(math.ceil((10 / eth_price) * 1000) / 1000, round(ekubo_eth_size - current_size, 3))

            limit_price = round(eth_price * 0.99, 1)

            try:
                order_result = self.exchange.order(
                    name="ETH",
                    is_buy=False,
                    sz=size_eth,
                    limit_px=limit_price,
                    order_type={"limit": {"tif": "Ioc"}},
                    reduce_only=False
                )

                if order_result.get("status") == "ok":
                    return True, order_result
                else:
                    return False, order_result
            except Exception as e:
                return False, str(e)

    def get_hl_positions(self):
        checksum_address = Web3.to_checksum_address(self.main_address)
        state = self.info.user_state(checksum_address)

        positions = state.get('assetPositions', [])
        if not positions:
            return None
        cur_position = positions[0]['position']
        return cur_position

    def get_ekubo_positions(self):
        RPC_URL = os.getenv("ETHEREUM_RPC_URL")
        w3 = Web3(Web3.HTTPProvider(RPC_URL))

        if not w3.is_connected():
            return False, "w3 is not connected"

        with open('ABI/PositionsABI.json', 'r') as f:
            positions_abi = json.load(f)

        positions_contract = w3.eth.contract(address=POSITIONS_CONTRACT, abi=positions_abi)

        pool_key = (TOKEN0, TOKEN1, CONFIG)
        bounds = (LOWER_TICK, UPPER_TICK)

        try:
            
            position_data = positions_contract.functions.getPositionFeesAndLiquidity(
                POSITION_ID,
                pool_key,
                bounds
            ).call()
            
            liquidity = position_data[0]
            principal0 = position_data[1]  # ETH
            principal1 = position_data[2]  # USDC
            fees0 = position_data[3]
            fees1 = position_data[4]
            
            eth_amount = principal0 / 10**18
            usdc_amount = principal1 / 10**6
            eth_fees = fees0 / 10**18
            usdc_fees = fees1 / 10**6

            return True, (eth_amount, usdc_amount)
        
        except Exception as e:
            return False, str(e)
    
    def get_ekubo_fees(self):
        RPC_URL = os.getenv("ETHEREUM_RPC_URL")
        w3 = Web3(Web3.HTTPProvider(RPC_URL))

        if not w3.is_connected():
            return False, "w3 is not connected"

        with open('ABI/PositionsABI.json', 'r') as f:
            positions_abi = json.load(f)

        positions_contract = w3.eth.contract(address=POSITIONS_CONTRACT, abi=positions_abi)

        pool_key = (TOKEN0, TOKEN1, CONFIG)
        bounds = (LOWER_TICK, UPPER_TICK)

        try:
            
            position_data = positions_contract.functions.getPositionFeesAndLiquidity(
                POSITION_ID,
                pool_key,
                bounds
            ).call()
            
            liquidity = position_data[0]
            principal0 = position_data[1]  # ETH
            principal1 = position_data[2]  # USDC
            fees0 = position_data[3]
            fees1 = position_data[4]
            
            eth_amount = principal0 / 10**18
            usdc_amount = principal1 / 10**6
            eth_fees = fees0 / 10**18
            usdc_fees = fees1 / 10**6

            return True, (eth_fees, usdc_fees)
        
        except Exception as e:
            return False, str(e)


    def check_to_change_position(self):
        success, data = self.get_ekubo_positions()

        if success:
            if data[0] < 0.001:
                self.cur_eth_size = data[0]
                return True, "place_min_short"
            elif data[1] < 1:
                self.cur_eth_size = data[0]
                return True, "place_max_short"

        if success:
            if abs(self.cur_eth_size - data[0]) > self.deviation:
                if self.cur_eth_size > data[0]:
                    self.cur_eth_size = data[0]
                    return True, "decrease"
                else:
                    self.cur_eth_size = data[0]
                    return True, "increase"
            else:
                return False, "no_change"
        else:
            return False, data

    def start_control_loop(self):
        self.control_loop_flag = True
    
    def stop_control_loop(self):
        self.control_loop_flag = False
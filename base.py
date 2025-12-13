import asyncio
import time
from collections import deque


async def keepalive_ping(websocket):
    """Send pings periodically to keep the WebSocket connection alive."""
    try:
        while True:
            await websocket.ping()
            # print("Sent keepalive ping.")
            await asyncio.sleep(30)  # Send a ping every 30 seconds
    except asyncio.CancelledError:
        print("Ping task cancelled.")

class PumpTrade:

    __slots__ = ("pool", "sol_price", "mint", "trader", "type", "token_amount", "sol_amount", "usd_amount",
                 "market_cap_sol", "market_cap_usd", "token_price", "token_balance_remaining")

    def __init__(self, data, sol_price=133):
        self.pool = data["pool"]
        self.sol_price = sol_price
        self.mint = data["mint"]
        self.trader = data["traderPublicKey"]
        self.type = data["txType"]
        self.token_amount = data["tokenAmount"]
        self.sol_amount = data["solAmount"]
        self.usd_amount = self.sol_amount * self.sol_price
        self.market_cap_sol = data["marketCapSol"]
        self.market_cap_usd = self.market_cap_sol * self.sol_price
        self.token_price = self.market_cap_usd / 1000000000


class RequestRateCounter:
    def __init__(self, window_size=1.0):
        self.timestamps = deque()
        self.window_size = window_size  # in seconds

    def record_request(self):
        now = time.time()
        self.timestamps.append(now)

        # Remove timestamps outside the time window
        while self.timestamps and self.timestamps[0] < now - self.window_size:
            self.timestamps.popleft()

    def get_rps(self):
        # Requests in the current window
        return len(self.timestamps)


class TokenStats:

    buys: int
    sells: int
    tx_sec: int
    dev_sold: bool
    entering_time: float
    entering_mcap: float
    entering_price: float
    token_amount: float
    buys_sells_ratio: float
    total_trades: int
    current_mcap: float
    trade_entered: bool
    exhausted: bool
    mint: str
    avg_buy_amount: float
    total_buy_volume: float
    last_trade_time: float
    mcap_logs: list[float]
    mcap_timestamp_logs: list[float]
    slope: float
    trend_strength: float
    first_five_buys: list[float]
    executing_order: bool
    pool: str

    def __init__(self):
        self.counter = RequestRateCounter()
        self.buys = 0
        self.sells = 0
        self.tx_sec = 0
        self.dev_sold = False
        self.entering_time = 0
        self.entering_mcap = 0
        self.entering_price = 0
        self.token_amount = 0
        self.buys_sells_ratio = 1
        self.total_trades = 0
        self.current_mcap = 0
        self.trade_entered = False
        self.exhausted = False
        self.mint = ""
        self.avg_buy_amount = 0
        self.total_buy_volume = 0
        self.last_trade_time = 0
        self.mcap_logs = []
        self.mcap_timestamp_logs = []
        self.slope = 0
        self.trend_strength = 0
        self.first_five_buys = []
        self.executing_order = False
        self.pool = "auto"

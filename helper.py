import operator
import os
import sys
import random
from base import TokenStats


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


ops = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    "is": operator.is_,
    "is not": operator.is_not,
}

props = {"total trades": "total_trades",
         "transaction/sec": "tx_sec",
         "buys": "buys",
         "sells": "sells",
         "buy/sell ratio": "buys_sells_ratio",
         "mcap": "current_mcap",
         "mcap slope": "slope",
         "trend strength": "trend_strength",
         "avg buy amount": "avg_buy_amount",
         "time elapsed": "time_elapsed",
         "PnL": "pnl"}


def format_duration(seconds) -> str:
    seconds = round(seconds, 2)
    if seconds < 60:
        return f"{seconds} s"

    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours > 0:
        parts.append(f"{round(hours)} h")
    if minutes > 0:
        parts.append(f"{round(minutes)} m")
    if sec > 0:
        parts.append(f"{round(sec)} s")

    return " ".join(parts)


def simulate_trade_finalization_time(priority_fee: float):
    """
    Simulate the time (in seconds) needed for a Solana trade to finalize.

    Args:
        priority_fee (float): priority fee in SOL.

    Returns:
        float: simulated time delay in seconds.
    """
    # --- network latency (propagation + RPC jitter) ---
    latency = max(0, random.gauss(0.25, 0.08))  # mean 250ms, std 80ms

    # --- inclusion time (faster with higher fee) ---
    # rate = base speed + boost from fee
    alpha = 0.35  # base inclusion rate (1/s)
    beta = 6000.0  # effect of fee on inclusion rate
    rate = alpha + beta * priority_fee

    # exponential draw for inclusion
    inclusion_time = random.expovariate(rate)

    # cap long waits (simulate retries with bumped fee)
    max_wait = 1.2  # if > this, assume resubmit
    resubmit_delay = 0.15
    retries = 0
    total_time = latency

    while inclusion_time > max_wait and retries < 3:
        # add failed wait + resubmit penalty
        total_time += max_wait + resubmit_delay
        retries += 1
        priority_fee *= 2  # bump fee
        rate = alpha + beta * priority_fee
        inclusion_time = random.expovariate(rate)
        latency = max(0.0, random.gauss(0.25, 0.08))
        total_time += latency

    # if included
    total_time += inclusion_time + 0.05  # small processing overhead

    return total_time, priority_fee + (retries * priority_fee)


def evaluate_conditions(token_stats: TokenStats, conditions, **kwargs):
    cond_count_tracker = 0
    pnl = kwargs.get("pnl")  # will be present only when selling
    time_elapsed = kwargs.get("time_elapsed")  # -||-
    for cond in conditions:
        cond_count_tracker += 1
        cond_satisfied = True
        for subcond in cond:
            prop = props[subcond[0]]
            op = subcond[1]
            value = subcond[2]

            if op not in ops:
                raise ValueError(f"Unsupported operator: {op}")

            if prop == "pnl":
                if not ops[op](pnl, value):
                    cond_satisfied = False
                    break
            elif prop == "time_elapsed":
                if not ops[op](time_elapsed, value):
                    cond_satisfied = False
                    break
            elif not ops[op](getattr(token_stats, prop), value):
                cond_satisfied = False
                break

        if cond_satisfied:
            return True, cond_count_tracker
    return False, None

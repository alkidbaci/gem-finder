import sys
import json
import asyncio
from collections import Counter
from copy import copy
from datetime import datetime
import websockets
import time
from types import SimpleNamespace
import requests
from PyQt6.QtCore import Qt, QSize, QSettings, QUrl
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QToolBar, QMainWindow, QTextEdit,
    QDialog, QDoubleSpinBox, QSpinBox, QComboBox, QScrollArea, QSizePolicy, QFormLayout, QFrame,
    QStackedWidget, QTextBrowser, QFileDialog, QMessageBox, QGroupBox, QCheckBox
)
from qasync import QEventLoop, asyncSlot
from PyQt6.QtGui import QAction, QIcon, QActionGroup
import markdown
from PyQt6.QtCharts import QChart, QChartView, QPieSeries
from scipy.stats import linregress
from base import TokenStats, keepalive_ping
from PyQt6.QtWebEngineWidgets import QWebEngineView
from helper import resource_path, format_duration, simulate_trade_finalization_time, evaluate_conditions
from keypair_import import KeypairImportWidget
from rpc_calls import get_balance, complete_official_transaction

MAX_LINES = 1000
TRANSACTION_FEE = 0.000005  # sol

first_response = True
queue = asyncio.Queue()
devs = dict()
tokens = dict()
subbed_tokens_count = 0
records_of_current_subbed_tokens = list()
strategy_transcript = dict()

# statistics
time_in_trade_sum = 0
tokens_created_since_start = 0
tokens_evaluated_since_start = 0
total_trades_record = 0
pnl_sum = 0
profitable_trades = 0


def reset_globals():
    global first_response
    global devs
    global tokens
    global subbed_tokens_count
    global records_of_current_subbed_tokens
    global strategy_transcript
    global time_in_trade_sum
    global tokens_created_since_start
    global tokens_evaluated_since_start
    global total_trades_record
    global pnl_sum
    global profitable_trades

    first_response = True
    devs = dict()
    tokens = dict()
    subbed_tokens_count = 0
    records_of_current_subbed_tokens = list()
    strategy_transcript = dict()
    time_in_trade_sum = 0
    tokens_created_since_start = 0
    tokens_evaluated_since_start = 0
    total_trades_record = 0
    pnl_sum = 0
    profitable_trades = 0


# === Async logic ===

async def receiver(ws):
    global first_response
    while True:
        response = await ws.recv()
        data = json.loads(response)
        # sometimes the creation call comes before the token trade successful subscription message, therefore this check
        if first_response and "txType" not in data.keys():
            print(data)
            print("\n")
            first_response = False
        else:
            await queue.put(data)


async def sub_token_trade(ws, token):
    global first_response
    first_response = True
    payload = {
        "method": "subscribeTokenTrade",
        "keys": [token]
    }
    print(token)

    await ws.send(json.dumps(payload))


def enter_trade(token: TokenStats, condition_no: int, buy_amount: float, sol_balance_widget, loggers, fees: float,
                use_imported_wallet: bool = False, cfg=None):

    if use_imported_wallet:
        retries = complete_official_transaction("buy", token.mint, cfg.keypair, cfg.max_slippage, cfg.priority_fee,
                                                "true", token.pool, buy_amount, cfg.rpc_url, loggers)
        sol_spent = buy_amount + TRANSACTION_FEE + cfg.priority_fee + (retries * (cfg.priority_fee + TRANSACTION_FEE))
    else:
        sol_spent = buy_amount + TRANSACTION_FEE + fees
    sol_balance = sol_balance_widget.value()
    token.trade_entered = True
    token.entering_time = time.time()
    token.last_trade_time = time.time()
    token.entering_mcap = token.current_mcap
    token.entering_price = token.current_mcap / 1000000000
    token.token_amount = buy_amount / token.entering_price
    sol_balance -= sol_spent
    sol_balance_widget.setValue(sol_balance)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    action = f"<span style='color: green;'>BUY</span>"
    amount = f"Amount: {token.token_amount:.2f}"
    token_mint = f"Token: {token.mint}"
    mcap = f"Mcap: {round(token.current_mcap, 2)}"
    sol_value = f"SOL value: {round(sol_spent, 6)}"
    new_balance = f"New balance: {round(sol_balance, 2)}"
    condition = f"Enter condition: {condition_no}"
    msg = f"{timestamp:<19} | {action:<10} | {amount:<25} | {token_mint:<100} | {mcap:<25} | {sol_value:<21} | {new_balance:<25} | {condition:<20}"

    loggers.log_transaction_message(msg)
    return token


def exit_trade(token: TokenStats, condition_no: int, buy_amount: float, sol_balance_widget, loggers, fees: float = 0,
               use_imported_wallet: bool = False, cfg=None):
    global total_trades_record
    global time_in_trade_sum
    global pnl_sum
    global profitable_trades

    if use_imported_wallet:
        retries = complete_official_transaction("sell", token.mint, cfg.keypair, cfg.max_slippage, cfg.priority_fee,
                                                "false", token.pool, "100%", cfg.rpc_url, loggers)
        current_price = token.current_mcap / 1000000000
        profit = (token.token_amount * current_price) - (TRANSACTION_FEE + cfg.priority_fee +
                                                         (retries * (cfg.priority_fee + TRANSACTION_FEE)))
    else:
        current_price = (token.current_mcap + buy_amount) / 1000000000  # adding 'buy_amount' just to simulate our trade
        profit = (token.token_amount * current_price) - (TRANSACTION_FEE + fees)

    sol_balance = sol_balance_widget.value()
    sol_balance += profit
    sol_balance_widget.setValue(sol_balance)
    pnl = ((token.current_mcap - token.entering_mcap) / token.entering_mcap) * 100
    token.exhausted = True
    token.trade_entered = False

    total_trades_record += 1
    time_in_trade_sum += time.time() - token.entering_time
    pnl_sum += pnl
    if pnl > 0:
        profitable_trades += 1

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    action = "<span style='color: red;'>SELL</span>"
    amount = f"Amount: {token.token_amount:.2f}"
    token_mint = f"Token: {token.mint}"
    mcap = f"Mcap: {round(token.current_mcap, 2)}"
    sol_value = f"SOL value: {round(profit, 6)}"
    new_balance = f"New balance: {round(sol_balance, 2)}"
    condition = f"Exit condition: {condition_no}"
    pnl_color = "#50C878" if pnl >= 0 else "#ff8080"
    msg = f"{timestamp:<19} | {action:<10} | {amount:<30} | {token_mint:<100} | {mcap:<25} | {sol_value:<21} | {new_balance:<25} | {condition:<20} | PnL: <span style='color: {pnl_color};'>{pnl:+.2f}%</span>"

    loggers.log_transaction_message(msg)
    return token


def update_values(token: TokenStats, data):
    token.counter.record_request()
    token.tx_sec = token.counter.get_rps()
    token.current_mcap = data["marketCapSol"]
    token.mcap_logs.append(token.current_mcap)
    token.mcap_timestamp_logs.append(time.time())
    if len(token.mcap_logs) > 2:
        # Measure the trend slope (units per second) and the trend strength
        base_time = token.mcap_timestamp_logs[0]
        x = [t - base_time for t in token.mcap_timestamp_logs]
        if len(set(x)) == 1 and len(x) > 1:
            x[-1] = x[-2] + 1
        y = token.mcap_logs
        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        token.slope = slope
        token.trend_strength = r_value**2
    if data["txType"] == "buy":
        token.buys += 1
        token.total_buy_volume += data["solAmount"]
        token.avg_buy_amount = token.total_buy_volume / token.buys
    elif data["txType"] == "sell":
        token.sells += 1
    else:
        print(data)
    if data["traderPublicKey"] == devs[token.mint] and data["txType"] == "sell":
        token.dev_sold = True
    try:
        token.pool = data["pool"]
    except KeyError:
        pass
    token.total_trades = token.buys + token.sells
    token.buys_sells_ratio = token.buys / token.sells if token.sells != 0 else 1
    token.last_trade_time = time.time()

    return token


async def simulate_trade_finalization(operation, mcap, mint, cond_no, cfg, loggers):
    global tokens
    global strategy_transcript

    delay, fees = simulate_trade_finalization_time(priority_fee=cfg.priority_fee)

    await asyncio.sleep(delay)  # simulate transaction execution time (network latency, inclusion time, retries, etc.)

    current_mcap = tokens[mint].current_mcap
    token = tokens[mint]
    price_movement = ((current_mcap - mcap) / current_mcap) * 100

    if operation == "buy":
        if price_movement < cfg.max_slippage:
            tokens[mint] = enter_trade(token, cond_no, cfg.buy_size, cfg.sol_balance_widget, loggers, fees)
            strategy_transcript[mint] = (cond_no, 0)  # store enter and exit condition for backtracking
            token.trade_entered = True
            token.executing_order = False
        else:
            token.executing_order = False
    elif operation == "sell":
        if -1 * price_movement < cfg.max_slippage:
            tokens[mint] = exit_trade(tokens[mint], cond_no, cfg.buy_size, cfg.sol_balance_widget, loggers, fees)
            strategy_transcript[mint] = (strategy_transcript[mint][0], cond_no)
        else:
            token.executing_order = False


async def processor(websocket, enter_conditions, exit_conditions, cfg, use_imported_wallet, loggers):
    global devs
    global first_response
    global subbed_tokens_count
    global tokens
    global records_of_current_subbed_tokens
    global strategy_transcript
    global tokens_created_since_start
    global tokens_evaluated_since_start

    while True:
        data = await queue.get()
        try:
            try_to_access_data = data["txType"]
        except KeyError:
            continue
        if data["txType"] == "create":  # on token creation search for tokens to subscribe to
            tokens_created_since_start += 1
            try:
                mint = data['mint']
            except KeyError as e:
                print(f"KeyError with: {data}")
                print(e)
                exit(1)
            if subbed_tokens_count < cfg.batch_reset_size:
                subbed_tokens_count += 1
                tokens_evaluated_since_start += 1
                devs[data["mint"]] = data["traderPublicKey"]
                records_of_current_subbed_tokens.append(mint)
                await sub_token_trade(websocket, mint)

        else:
            mint = data["mint"]
            if mint not in tokens:
                tokens[mint] = TokenStats()
                tokens[mint].mint = mint
                tokens[mint] = update_values(tokens[mint], data)
            elif not tokens[mint].exhausted:
                tokens[mint] = update_values(tokens[mint], data)
                token = tokens[mint]
                if not token.trade_entered:
                    # ===== TRADE ENTER =====
                    any_cond_satisfied, cond_no = evaluate_conditions(token, enter_conditions)
                    if any_cond_satisfied and not token.executing_order:
                        if cfg.sol_balance_widget.value() > cfg.buy_size:
                            token.executing_order = True
                            if not use_imported_wallet:
                                asyncio.create_task(simulate_trade_finalization("buy", token.current_mcap, mint, cond_no, cfg, loggers))
                            else:
                                try:
                                    tokens[mint] = enter_trade(token, cond_no, cfg.buy_size, cfg.sol_balance_widget, loggers,
                                                               0, use_imported_wallet, cfg)
                                    strategy_transcript[mint] = (cond_no, 0)  # store enter and exit condition for backtracking
                                    token.trade_entered = True
                                    token.executing_order = False
                                except Exception as e:
                                    loggers.log_general_message(f"Error during trade entry for token {mint}: {e}")
                                    token.executing_order = False
                        else:
                            loggers.log_general_message(f"Insufficient SOL balance to enter trade for token {mint}."
                                                        f" Needed: {cfg.buy_size}, "
                                                        f"Available: {cfg.sol_balance_widget.value()}")

                else:
                    # ===== TRADE EXIT =====
                    mcap = token.current_mcap
                    entering_mcap = token.entering_mcap
                    time_elapsed = time.time() - token.entering_time
                    tx_sec = token.tx_sec
                    pnl = ((mcap - entering_mcap) / entering_mcap) * 100
                    pnl_str = f"{pnl:+.2f}%"

                    any_cond_satisfied, cond_no = evaluate_conditions(token, exit_conditions, pnl=pnl,
                                                                      time_elapsed=time_elapsed)
                    if any_cond_satisfied and not token.executing_order:
                        token.executing_order = True
                        if not use_imported_wallet:
                            asyncio.create_task(simulate_trade_finalization("sell", mcap, mint, cond_no, cfg, loggers))
                        else:
                            try:
                                tokens[mint] = exit_trade(tokens[mint], cond_no, cfg.buy_size, cfg.sol_balance_widget,
                                                          loggers, 0, use_imported_wallet, cfg)
                                strategy_transcript[mint] = (strategy_transcript[mint][0], cond_no)
                                token.executing_order = False
                            except Exception as e:
                                loggers.log_general_message(f"Error during trade exit for token {mint}: {e}")
                                token.executing_order = False
                        continue

                    loggers.log_general_message(f"token: {mint} | tx/sec: {tx_sec} | buys/sells: {token.buys} / {token.sells} | "
                                                f"mcap: {round(mcap, 2)} | avg_buy: {round(token.avg_buy_amount, 2)} | "
                                                f"slope: {round(token.slope, 2)} | strength: {round(token.trend_strength, 2)} | "
                                                f"PnL: {pnl_str} | time_elapsed: {round(time_elapsed, 2)} | dev_sold: {token.dev_sold}")


async def discard_current_batch(websocket, batch_reset_size, loggers):
    global subbed_tokens_count
    global first_response
    global tokens
    global records_of_current_subbed_tokens
    try:
        while True:
            if subbed_tokens_count >= batch_reset_size:
                trade_active = False
                mints = list()
                for mint, token in tokens.items():
                    mints.append(mint)
                    if token.trade_entered:
                        trade_active = True
                if not trade_active:
                    payload = {
                        "method": "unsubscribeTokenTrade",
                        "keys": mints
                    }
                    first_response = True
                    await websocket.send(json.dumps(payload))
                    tokens = dict()
                    subbed_tokens_count = 0
                    loggers.log_general_message("* Discarded old batch, looking for new tokens... *")
                    records_of_current_subbed_tokens = list(set(records_of_current_subbed_tokens) - set(mints))
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        print("Discarding token batches task canceled.")


async def sell_stale_tokens(threshold, buy_amount, sol_balance_widget, use_imported_wallet, cfg, loggers):
    global tokens
    try:
        while True:
            for mint, token in tokens.items():
                if token.trade_entered:
                    if time.time() - token.last_trade_time >= threshold and not token.executing_order:
                        if use_imported_wallet:
                            tokens[mint] = exit_trade(token, 101, buy_amount, sol_balance_widget,
                                                      loggers, 0, use_imported_wallet, cfg)
                        else:
                            # no delay is added to this trade because this token is supposed to have no activity
                            # by the time we want to sell and there is a very low chance that a transaction will
                            # happen during the time our exit trade finalizes.
                            tokens[mint] = exit_trade(token, 101, buy_amount, sol_balance_widget, loggers)
                        strategy_transcript[mint] = (strategy_transcript[mint][0], 101)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print("Canceled stale token selling task.")


def exit_trades(cfg, use_imported_wallet, loggers):
    global tokens
    for mint, token in tokens.items():
        if token.trade_entered and not token.executing_order:
            if use_imported_wallet:
                tokens[mint] = exit_trade(token, 100, cfg.buy_size, cfg.sol_balance_widget, loggers, 0,
                                          use_imported_wallet, cfg)
            else:
                tokens[mint] = exit_trade(token, 100, cfg.buy_size, cfg.sol_balance_widget, loggers)
            strategy_transcript[mint] = (strategy_transcript[mint][0], 100)


async def subscribe(enter_conditions, exit_conditions, loggers, cfg, use_imported_wallet: bool = False):
    global records_of_current_subbed_tokens
    global strategy_transcript
    uri = "wss://pumpportal.fun/api/data"
    async with websockets.connect(uri) as websocket:
        payload = {"method": "subscribeNewToken"}
        await websocket.send(json.dumps(payload))
        try:
            await asyncio.gather(
                receiver(websocket),
                processor(websocket, enter_conditions, exit_conditions, cfg, use_imported_wallet, loggers),
                keepalive_ping(websocket),
                discard_current_batch(websocket, cfg.batch_reset_size, loggers),
                sell_stale_tokens(cfg.inactivity_reset_time, cfg.buy_size, cfg.sol_balance_widget,
                                  use_imported_wallet, cfg, loggers)
            )
        # except asyncio.CancelledError:
        except Exception as e:
            print(f"Error: {e}")
            raise
        finally:
            exit_trades(cfg, use_imported_wallet, loggers)
            payload = {
                "method": "unsubscribeNewToken",
            }
            await websocket.send(json.dumps(payload))
            print("Unsubscribed from new token event")
            time.sleep(1)
            payload = {
                "method": "unsubscribeTokenTrade",
                "keys": records_of_current_subbed_tokens
            }
            await websocket.send(json.dumps(payload))
            print("Unsubscribed from tokens: {}".format(records_of_current_subbed_tokens))


# --- PyQt UI ---

class SubConditionRow(QWidget):
    def __init__(self, is_enter_condition: bool, remove_callback, current_sub_condition=None, parent=None):
        super().__init__(parent)
        self.remove_callback = remove_callback
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.operator_box = QComboBox()
        self.operator_box.addItems([">", ">=", "<", "<=", "==", "!="])
        self.properties = QComboBox()
        if is_enter_condition:
            self.properties.addItems(["total trades", "transaction/sec", "buys", "sells", "buy/sell ratio", "mcap", "mcap slope", "trend strength", "avg buy amount"])
        else:  # exit condition
            self.properties.addItems(["PnL", "time elapsed", "total trades", "transaction/sec", "buys", "sells", "buy/sell ratio", "mcap", "mcap slope", "trend strength", "avg buy amount"])

        self.value_input = QDoubleSpinBox()
        self.value_input.setMinimum(-100)
        self.value_input.setMaximum(10000)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setFixedWidth(80)
        self.remove_button.clicked.connect(self.remove_self)

        if current_sub_condition is not None:
            self.properties.setCurrentIndex(self.properties.findText(current_sub_condition[0]))
            self.operator_box.setCurrentIndex(self.operator_box.findText(current_sub_condition[1]))
            self.value_input.setValue(current_sub_condition[2])

        layout.addWidget(self.properties)
        layout.addWidget(self.operator_box)
        layout.addWidget(self.value_input)
        layout.addWidget(self.remove_button)

        self.setLayout(layout)

    def get_sub_condition(self):
        return self.properties.currentText(), self.operator_box.currentText(), self.value_input.value()

    def remove_self(self):
        self.remove_callback(self)


class ConditionRow(QWidget):
    def __init__(self, remove_callback, condition, edit_condition_callback, is_enter_condition, parent=None):
        super().__init__(parent)
        self.condition = condition
        self.is_enter_condition = is_enter_condition
        condition_content = ""
        for sub_cond in condition:
            condition_content += str(sub_cond[0]) + " " + str(sub_cond[1]) + " " + str(sub_cond[2]) + "\n"
        self.remove_callback = remove_callback
        self.edit_condition_callback = edit_condition_callback
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.info_box.setText(condition_content)
        self.info_box.setFixedHeight(55)

        buttons = QVBoxLayout()

        remove_button = QPushButton("Remove")
        remove_button.setFixedWidth(60)
        remove_button.clicked.connect(self.remove_self)
        edit_button = QPushButton("Edit")
        edit_button.setFixedWidth(60)
        edit_button.clicked.connect(self.edit_condition)
        buttons.addWidget(edit_button)
        buttons.addWidget(remove_button)

        layout.addWidget(self.info_box)
        layout.addLayout(buttons)

        self.setLayout(layout)

    def get_condition_as_text(self):
        return self.info_box.toPlainText()

    def remove_self(self):
        self.remove_callback(self)

    def edit_condition(self):
        self.edit_condition_callback(self.is_enter_condition, self)


class ConditionDialog(QDialog):
    def __init__(self, is_enter_condition: bool, current_condition_row=None, parent=None):
        self.is_enter_condition = is_enter_condition
        super().__init__(parent)
        self.setWindowTitle("Define Conditions")
        self.setMinimumWidth(400)
        self.resize(800, 600)

        self.sub_conditions = []

        self.main_layout = QVBoxLayout()

        # Scroll area to contain multiple rows
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_container = QWidget()
        self.scroll_layout = QVBoxLayout()
        self.scroll_container.setLayout(self.scroll_layout)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_container)
        self.main_layout.addWidget(QLabel("Set your condition:"))
        self.main_layout.addWidget(self.scroll_area)

        # Buttons
        self.add_button = QPushButton("Add")
        self.submit_button = QPushButton("Save")

        self.add_button.clicked.connect(lambda: self.add_sub_condition_row(None))
        self.submit_button.clicked.connect(self.submit_conditions)

        button_layout = QHBoxLayout()
        # button_layout.addWidget(self.add_button)
        button_layout.addStretch()
        button_layout.addWidget(self.submit_button)

        self.main_layout.addLayout(button_layout)
        self.setLayout(self.main_layout)
        if current_condition_row is not None:
            for sub_condition in current_condition_row.condition:
                self.add_sub_condition_row(sub_condition)
        else:
            self.add_sub_condition_row()  # Add initial sub-condition
        self.scroll_layout.addWidget(self.add_button)

    def add_sub_condition_row(self, current_sub_condition=None):
        row = SubConditionRow(is_enter_condition=self.is_enter_condition, current_sub_condition=current_sub_condition,
                              remove_callback=self.remove_condition_row)
        self.sub_conditions.append(row)
        index = self.scroll_layout.indexOf(self.add_button)
        self.scroll_layout.insertWidget(index, row)

    def remove_condition_row(self, row):
        if len(self.sub_conditions) > 1:
            self.scroll_layout.removeWidget(row)
            row.setParent(None)
            self.sub_conditions.remove(row)

    def submit_conditions(self):
        self.result = [row.get_sub_condition() for row in self.sub_conditions]
        self.accept()  # Closes the dialog

    def get_sub_conditions(self):
        return getattr(self, "result", [])


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()


        self.current_keypair = None
        self.enter_conditions_for_report = None
        self.exit_conditions_for_report = None
        self.report_layout_charts = None
        self.report_layout_conditions_info = None
        self.report_layout = None
        self.loggers = None
        self.cfg = None
        self.setWindowTitle("Gem Finder")
        self.setWindowIcon(QIcon(resource_path("images/tourmaline.png")))
        self.stacked = QStackedWidget()
        self.settings = QSettings("Alkid", "Gem-finder")
        self.uptime = 0
        self.pnl_to_report = None

        self.sniper_widget = QWidget()
        self.copy_trade_widget = QWidget()
        self.info_widget = QWidget()
        self.report_widget = QWidget()
        self.pump_fun_widget = QWidget()
        self.solana_wallet_widget = QWidget()

        self.layout1 = QHBoxLayout()
        self.layout_left = QVBoxLayout()
        self.layout_left_enter = QVBoxLayout()
        self.layout_left_exit = QVBoxLayout()
        self.layout_right = QVBoxLayout()

        # ===================================== MENU BAR ======================================

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        # edit_menu = menubar.addMenu("Edit")
        # view_menu = menubar.addMenu("View")

        import_action = file_menu.addAction("Import")
        export_action = file_menu.addAction("Export")
        reset_defaults_action = file_menu.addAction("Reset Defaults")
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)
        reset_defaults_action.triggered.connect(self.reset_to_default_state)
        export_action.triggered.connect(self.export_state)
        import_action.triggered.connect(self.import_state)

        # todo: implement these 3 actions down below

        # copy_action = edit_menu.addAction("Copy")
        # paste_action = edit_menu.addAction("Paste")
        # toggle_action = view_menu.addAction("Do something")

        # ====================================== NAVBAR ======================================
        toolbar = QToolBar("Quick-access bar")
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)

        self.nav_action_group = QActionGroup(self)
        self.nav_action_group.setExclusive(True)

        self.sniper_button_action = QAction(QIcon(resource_path("images/sniper.png")), "Sniper Window", self)
        self.sniper_button_action.setStatusTip("See list of all newly created tokens.")
        self.sniper_button_action.triggered.connect(lambda: self.stacked.setCurrentIndex(0))
        self.sniper_button_action.setCheckable(True)
        self.sniper_button_action.setChecked(True)
        self.nav_action_group.addAction(self.sniper_button_action)

        self.copy_trade_button_action = QAction(QIcon(resource_path("images/copy_trade.png")), "Copy Trade Window", self)
        self.copy_trade_button_action.triggered.connect(lambda: self.stacked.setCurrentIndex(1))
        self.copy_trade_button_action.setCheckable(True)
        self.nav_action_group.addAction(self.copy_trade_button_action)

        self.report_button_action = QAction(QIcon(resource_path("images/report.png")), "Reports", self)
        self.report_button_action.triggered.connect(lambda: self.stacked.setCurrentIndex(2))
        self.report_button_action.setCheckable(True)
        self.nav_action_group.addAction(self.report_button_action)

        self.pump_fun_button_action = QAction(QIcon(resource_path("images/pumpfun.png")), "pump.fun", self)
        self.pump_fun_button_action.triggered.connect(lambda: self.stacked.setCurrentIndex(3))
        self.pump_fun_button_action.setCheckable(True)
        self.nav_action_group.addAction(self.pump_fun_button_action)

        self.solana_wallet_button_action = QAction(QIcon(resource_path("images/solana_wallet.png")), "Wallet", self)
        self.solana_wallet_button_action.triggered.connect(lambda: self.stacked.setCurrentIndex(4))
        self.solana_wallet_button_action.setCheckable(True)
        self.nav_action_group.addAction(self.solana_wallet_button_action)

        self.information_button_action = QAction(QIcon(resource_path("images/information.png")), "Help", self)
        self.information_button_action.triggered.connect(lambda: self.stacked.setCurrentIndex(5))
        self.information_button_action.setCheckable(True)
        self.nav_action_group.addAction(self.information_button_action)

        toolbar.addAction(self.sniper_button_action)
        toolbar.addAction(self.copy_trade_button_action)
        toolbar.addAction(self.report_button_action)
        toolbar.addAction(self.pump_fun_button_action)
        toolbar.addAction(self.solana_wallet_button_action)
        toolbar.addAction(self.information_button_action)

        # ====================================== INFO WIDGET SETUP ======================================

        with open(resource_path("instructions.md"), "r", encoding="utf-8") as input_file:
            md_text = input_file.read()
        html_body = markdown.markdown(md_text)
        browser = QTextBrowser()
        html = f"""
        <html>
            <head>
                <style>
                    body {{margin: 50px;}}
                </style>
            </head>
            <body>
                {html_body}
            </body>
        </html>
        """
        browser.setHtml(html)
        self.info_widget.setLayout(QVBoxLayout())
        self.info_widget.layout().addWidget(browser)
        browser.setMaximumWidth(1100)
        self.info_widget.layout().setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # ====================================== COPY TRADE WIDGET SETUP ======================================

        self.copy_trade_widget.setLayout(QVBoxLayout())
        self.copy_trade_widget.layout().addWidget(QLabel("Copy-trading bot is not currently available through the app."
                                                         "<br>You can use it through the command line interface."))
        self.copy_trade_widget.layout().setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # ====================================== REPORT WIDGET SETUP ======================================

        self.report_widget_layout = QHBoxLayout()
        self.report_scroll_area = QScrollArea()
        self.report_scroll_area.setWidgetResizable(True)
        self.report_scroll_container = QWidget()

        self.report_layout = QHBoxLayout()
        self.report_layout_conditions_info = QVBoxLayout()
        self.report_layout_charts = QVBoxLayout()

        info_chart_line = QFrame()
        info_chart_line.setFrameShape(QFrame.Shape.VLine)
        info_chart_line.setFrameShadow(QFrame.Shadow.Sunken)

        self.report_layout.addLayout(self.report_layout_conditions_info, 1)
        self.report_layout.addWidget(info_chart_line)
        self.report_layout.addLayout(self.report_layout_charts, 3)

        self.report_scroll_container.setLayout(self.report_layout)
        self.report_scroll_area.setWidget(self.report_scroll_container)
        self.report_widget_layout.addWidget(self.report_scroll_area)
        self.report_widget.setLayout(self.report_widget_layout)

        # ====================================== PUMP WEB VIEWER SETUP ======================================

        pump_layout = QVBoxLayout()
        self.pump_fun_widget.setLayout(pump_layout)
        pump_web_view = QWebEngineView()
        pump_layout.addWidget(pump_web_view)

        url = QUrl.fromUserInput("https://pump.fun")
        pump_web_view.load(url)

        # ====================================== SOLANA WALLET WIDGET SETUP ======================================

        sww_layout = QVBoxLayout()
        self.solana_wallet_widget.setLayout(sww_layout)
        sww_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning = QLabel("<h2>Warning - Read carefully!</h2>")
        warning.setWordWrap(True)
        warning.setStyleSheet("font-family: monospace; padding: 5px;")

        warning_content = QLabel("Once you enter your keypair and tick the checkbox in the snipping tab, "
                                 "the bot will use your wallet to perform <b>real</b> trades.<br>"
                                 "Make sure you have stopped the bot first before importing your wallet.<br>"
                                 "For safety reasons, your wallet will not be stored when closing the application.<br>"
                                 "Be aware that performing real trades can lead to financial losses. "
                                 "Please proceed only if you know what you are doing. "
                                 "Also notice that the application can be prone to errors. It's not thoroughly "
                                 "tested and comes without warranty of any kind. Proceed at your own risk! <br><hr>")
        warning_content.setWordWrap(True)
        warning_content.setStyleSheet("font-family: monospace; padding: 5px;")
        warning_content.setMaximumWidth(600)
        sww_layout.addWidget(warning)
        sww_layout.addWidget(warning_content)

        self.keypair_widget = KeypairImportWidget()
        self.keypair_widget.keypair_imported.connect(self.on_keypair_ready)
        self.keypair_widget.setMaximumWidth(600)
        sww_layout.addWidget(self.keypair_widget)

        # ---------------------------------------- RPC URL ------------------------------------------
        rpc_url_title = QLabel("<hr><br>RPC Endpoint (optional)")
        rpc_url_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 5px;")
        self.rpc_url = QTextEdit()
        self.rpc_url.setPlaceholderText("E.g.: https://mainnet.helius-rpc.com/?api-key=<your-api-key>")
        self.rpc_url.textChanged.connect(self.validate_rpc_url)
        rpc_url_label = QLabel("By default the bot uses the public Solana RPC endpoint which is not very reliable.<br>"
                               "You can enter here a custom RPC endpoint (e.g. helius) to improve the performance.")
        rpc_url_label.setWordWrap(True)
        rpc_url_label.setStyleSheet("font-family: monospace; padding: 2px;")
        rpc_url_label.setMaximumWidth(600)
        self.rpc_url.setMaximumHeight(30)
        self.rpc_url.setMaximumWidth(600)
        self.rpc_url_validation_label = QLabel("")
        self.rpc_url_validation_label.setStyleSheet("color: red; font-size: 12px;")
        self.rpc_url_validation_label.setMaximumWidth(600)
        sww_layout.addWidget(rpc_url_title)
        sww_layout.addWidget(rpc_url_label)
        sww_layout.addWidget(self.rpc_url)
        sww_layout.addWidget(self.rpc_url_validation_label)
        sww_layout.addStretch()

        # ====================================== SNIPER WIDGET SETUP ======================================

        # ---------------------------------------- INPUT FIELDS ------------------------------------------

        # --- General inputs ---

        self.sol_balance = QDoubleSpinBox()
        self.sol_balance.setDecimals(5)
        self.entering_sol_balance = None
        self.sol_balance.setValue(5)
        self.sol_balance.setMaximum(1000)
        self.sol_balance.textChanged.connect(self.on_sol_balance_changed)
        self.max_slippage = QDoubleSpinBox()
        self.max_slippage.setValue(30)
        self.max_slippage.setMaximum(1000)
        self.buy_size = QDoubleSpinBox()
        self.buy_size.setDecimals(5)
        self.buy_size.setValue(0.3)
        self.buy_size.setMaximum(1000)
        self.priority_fee = QDoubleSpinBox()
        self.priority_fee.setDecimals(5)
        self.priority_fee.setValue(0)
        self.priority_fee.setMaximum(10)
        self.batch_reset_size = QSpinBox()
        self.batch_reset_size.setValue(10)
        self.batch_reset_size.setMaximum(100)
        self.inactivity_reset_time = QDoubleSpinBox()
        self.inactivity_reset_time.setMaximum(10000)
        self.inactivity_reset_time.setValue(3.9)

        self.general_inputs = QFormLayout()
        self.general_inputs.addRow("<b>Balance (sol):</b>", self.sol_balance)
        self.general_inputs.addRow("<b>Slippage (%):</b>", self.max_slippage)
        self.general_inputs.addRow("<b>Buy size (sol):</b>", self.buy_size)
        self.general_inputs.addRow("<b>Priority fee (sol):</b>", self.priority_fee)
        self.general_inputs.addRow("<b>Tokens before batch resets:</b>", self.batch_reset_size)
        self.general_inputs.addRow("<b>Time of inactivity before selling (sec):</b>", self.inactivity_reset_time)
        self.use_imported_wallet = QCheckBox("⚠️")
        self.use_imported_wallet.setToolTip("When checked, this will enable real trading using the imported wallet. Be aware of the risks!")
        self.use_imported_wallet.toggled.connect(self.use_imported_wallet_changed)
        self.general_inputs.addRow("<b>Use imported wallet:</b>", self.use_imported_wallet)



        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self.on_start)
        self.stop_button.clicked.connect(self.on_stop)

        # --- ENTER setup ---

        self.enter_label = QLabel("Entering Conditions")
        self.add_enter_condition_button = QPushButton(QIcon(resource_path("images/plus.png")), " Add", self)
        self.add_enter_condition_button.clicked.connect(lambda: self.add_or_edit_condition(True))

        self.enter_header = QHBoxLayout()
        self.enter_header.addWidget(self.enter_label)
        self.enter_header.addStretch()
        self.enter_header.addWidget(self.add_enter_condition_button)
        self.enter_header.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.enter_scroll_area = QScrollArea()
        self.enter_scroll_area.setWidgetResizable(True)
        self.enter_scroll_container = QWidget()
        self.enter_scroll_layout = QVBoxLayout()
        self.enter_scroll_container.setLayout(self.enter_scroll_layout)
        self.enter_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.enter_scroll_area.setWidget(self.enter_scroll_container)

        self.enter_conditions = []
        self.interpretable_enter_conditions = []

        # --- EXIT setup ---

        self.exit_label = QLabel("Exit Conditions")
        self.add_exit_condition_button = QPushButton(QIcon(resource_path("images/plus.png")), " Add", self)
        self.add_exit_condition_button.clicked.connect(lambda: self.add_or_edit_condition(False))

        self.exit_header = QHBoxLayout()
        self.exit_header.addWidget(self.exit_label)
        self.exit_header.addStretch()
        self.exit_header.addWidget(self.add_exit_condition_button)
        self.exit_header.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.exit_scroll_area = QScrollArea()
        self.exit_scroll_area.setWidgetResizable(True)
        self.exit_scroll_container = QWidget()
        self.exit_scroll_layout = QVBoxLayout()
        self.exit_scroll_container.setLayout(self.exit_scroll_layout)
        self.exit_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.exit_scroll_area.setWidget(self.exit_scroll_container)

        self.exit_conditions = []
        self.interpretable_exit_conditions = []

        # ---------------------------------------- OUTPUT FIELDS ------------------------------------------

        self.general_logs_output = QTextEdit()
        self.transaction_logs_output = QTextEdit()
        self.general_logs_output.setReadOnly(True)
        self.transaction_logs_output.setReadOnly(True)
        self.general_logs_label = QLabel("General Logs")
        self.buy_sell_logs_label = QLabel("Buy/Sell Logs")
        clear_buy_sell_logs_button = QPushButton("Clear")
        clear_general_logs_button = QPushButton("Clear")
        clear_buy_sell_logs_button.clicked.connect(lambda: self.transaction_logs_output.clear())
        clear_general_logs_button.clicked.connect(lambda: self.general_logs_output.clear())


        # ---------------------------------------- Start/Stop LAYOUT ------------------------------------------

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)

        input_output_line = QFrame()
        input_output_line.setFrameShape(QFrame.Shape.VLine)
        input_output_line.setFrameShadow(QFrame.Shadow.Sunken)

        self.start_stop_layout = QHBoxLayout()
        self.start_stop_layout.addWidget(self.stop_button)
        self.start_stop_layout.addStretch()
        self.status_label = QLabel("Status: Waiting for conditions")
        self.start_stop_layout.addWidget(self.status_label)
        self.start_stop_layout.addStretch()
        self.start_stop_layout.addWidget(self.start_button)

        # ====================================== PUTTING EVERYTHING TOGETHER ======================================

        self.layout_left_enter.addLayout(self.enter_header)
        self.layout_left_enter.addWidget(self.enter_scroll_area)

        self.layout_left_exit.addLayout(self.exit_header)
        self.layout_left_exit.addWidget(self.exit_scroll_area)

        self.layout_left.addLayout(self.general_inputs)
        self.layout_left.addSpacing(20)
        self.layout_left.addLayout(self.layout_left_enter)
        self.layout_left.addLayout(self.layout_left_exit)
        self.layout_left.addSpacing(20)
        self.layout_left.addWidget(line)
        self.layout_left.addSpacing(20)
        self.layout_left.addLayout(self.start_stop_layout)

        log_title_layout = QHBoxLayout()
        log_title_layout.addWidget(self.buy_sell_logs_label)
        log_title_layout.addStretch()
        log_title_layout.addWidget(clear_buy_sell_logs_button)
        general_logs_title_layout = QHBoxLayout()
        general_logs_title_layout.addWidget(self.general_logs_label)
        general_logs_title_layout.addStretch()
        general_logs_title_layout.addWidget(clear_general_logs_button)

        self.layout_right.addLayout(log_title_layout)
        self.layout_right.addWidget(self.transaction_logs_output, 1)
        self.layout_right.addLayout(general_logs_title_layout)
        self.layout_right.addWidget(self.general_logs_output, 3)

        self.layout1.addLayout(self.layout_left, 1)
        self.layout1.addWidget(input_output_line)
        self.layout1.addLayout(self.layout_right, 3)
        self.sniper_widget.setLayout(self.layout1)
        # self.setCentralWidget(self.sniper_widget)
        self.setCentralWidget(self.stacked)
        self.stacked.addWidget(self.sniper_widget)
        self.stacked.addWidget(self.copy_trade_widget)
        self.stacked.addWidget(self.report_widget)
        self.stacked.addWidget(self.pump_fun_widget)
        self.stacked.addWidget(self.solana_wallet_widget)
        self.stacked.addWidget(self.info_widget)

        self.task = None

        self.load_state()

    def on_sol_balance_changed(self, value):
        self.buy_size.setMaximum(float(value))

    def validate_rpc_url(self):
        """Validate the RPC URL and provide visual feedback"""
        url_text = self.rpc_url.toPlainText().strip()

        # If empty, it's valid (optional field)
        if not url_text:
            self.rpc_url.setStyleSheet("")
            self.rpc_url_validation_label.setText("")
            return True

        # Check if URL is valid
        url = QUrl(url_text)
        if url.isValid() and url.scheme() in ['http', 'https'] and url.host():
            # Valid URL
            self.rpc_url.setStyleSheet("")
            self.rpc_url_validation_label.setText("")
            return True
        else:
            # Invalid URL
            self.rpc_url.setStyleSheet("border: 2px solid red;")
            self.rpc_url_validation_label.setText("⚠ Invalid URL format. Please enter a valid HTTP/HTTPS URL.")
            self.rpc_url_validation_label.setStyleSheet("color: red; font-size: 12px;")
            return False

    async def test_rpc_endpoint(self, url: str) -> bool:
        """Test if the RPC endpoint is actually working by making a simple call"""
        try:
            # Create a simple JSON-RPC 2.0 call to get the cluster version
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getVersion",
                "params": []
            }

            headers = {
                "Content-Type": "application/json"
            }

            # Make the request with a 5-second timeout
            response = requests.post(url, json=payload, headers=headers, timeout=5)

            # Check if response is successful
            if response.status_code == 200:
                data = response.json()
                # Check if we got a valid JSON-RPC response
                if "result" in data or "error" not in data:
                    return True
                else:
                    self.log_general_message("⚠ RPC endpoint returned an error when validating it.")
                    return False
            else:
                self.log_general_message(f"⚠ RPC endpoint returned status code {response.status_code} "
                                         f"when validating it.")
                return False

        except requests.exceptions.Timeout:
            self.log_general_message("⚠ RPC endpoint timeout (5 seconds). Check your connection.")
            return False
        except requests.exceptions.ConnectionError:
            self.log_general_message("⚠ Cannot connect to RPC endpoint. Check the URL.")
            return False
        except Exception as e:
            self.log_general_message(f"⚠ Error testing RPC endpoint: {str(e)[:50]}")
            return False



    def add_condition_row(self, condition, is_enter_condition: bool, index=None):
        if is_enter_condition:
            row = ConditionRow(remove_callback=self.remove_enter_condition_row,
                               edit_condition_callback=self.add_or_edit_condition, condition=condition,
                               is_enter_condition=is_enter_condition)
            self.enter_conditions.append(row)
            if index is not None:
                self.enter_scroll_layout.insertWidget(index, row)
            else:
                self.enter_scroll_layout.addWidget(row)
        else:
            row = ConditionRow(remove_callback=self.remove_exit_condition_row,
                               edit_condition_callback=self.add_or_edit_condition, condition=condition,
                               is_enter_condition=is_enter_condition)
            self.exit_conditions.append(row)
            if index is not None:
                self.exit_scroll_layout.insertWidget(index, row)
            else:
                self.exit_scroll_layout.addWidget(row)

        if len(self.enter_conditions) > 0 and len(self.exit_conditions) > 0:
            self.status_label.setText("Status: Ready")

    def update_condition_row(self, new_condition, enter_condition: bool, previous_row: ConditionRow):
        index = self.get_condition_row_index(previous_row, enter_condition)
        self.add_condition_row(new_condition, enter_condition, index)
        previous_row.remove_self()

    def get_condition_row_index(self, row: ConditionRow, enter_condition: bool):
        if enter_condition:
            return self.enter_scroll_layout.indexOf(row)
        return self.exit_scroll_layout.indexOf(row)

    def get_enter_conditions(self):
        return self.interpretable_enter_conditions

    def get_exit_conditions(self):
        return self.interpretable_exit_conditions

    def remove_enter_condition_row(self, row):
        self.enter_scroll_layout.removeWidget(row)
        row.setParent(None)
        self.enter_conditions.remove(row)
        self.interpretable_enter_conditions.remove(row.condition)

        if not (len(self.enter_conditions) > 0 and len(self.exit_conditions) > 0):
            self.status_label.setText("Status: Waiting for conditions")

    def remove_exit_condition_row(self, row):
        self.exit_scroll_layout.removeWidget(row)
        row.setParent(None)
        self.exit_conditions.remove(row)
        self.interpretable_exit_conditions.remove(row.condition)

        if not (len(self.enter_conditions) > 0 and len(self.exit_conditions) > 0):
            self.status_label.setText("Status: Waiting for conditions")

    def add_or_edit_condition(self, is_enter_condition: bool, current_condition_row=None):
        dialog = ConditionDialog(is_enter_condition, current_condition_row)
        if dialog.exec():
            condition = dialog.get_sub_conditions()
            if is_enter_condition:
                self.interpretable_enter_conditions.append(condition)
            else:
                self.interpretable_exit_conditions.append(condition)
            if current_condition_row is None:
                self.add_condition_row(condition, is_enter_condition)
            else:
                self.update_condition_row(condition, is_enter_condition, current_condition_row)
        else:
            print("User cancelled.")

    def log_general_message(self, msg: str):
        self.general_logs_output.append(msg)

    def log_transaction_message(self, msg: str):
        self.transaction_logs_output.append(msg)

    def enable_interface(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.sol_balance.setEnabled(True)
        self.buy_size.setEnabled(True)
        self.max_slippage.setEnabled(True)
        self.priority_fee.setEnabled(True)
        self.batch_reset_size.setEnabled(True)
        self.inactivity_reset_time.setEnabled(True)
        self.use_imported_wallet.setEnabled(True)
        self.enter_scroll_container.setEnabled(True)
        self.exit_scroll_container.setEnabled(True)
        self.add_enter_condition_button.setEnabled(True)
        self.add_exit_condition_button.setEnabled(True)

    def disable_interface(self):
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.sol_balance.setEnabled(False)
        self.buy_size.setEnabled(False)
        self.max_slippage.setEnabled(False)
        self.priority_fee.setEnabled(False)
        self.batch_reset_size.setEnabled(False)
        self.inactivity_reset_time.setEnabled(False)
        self.use_imported_wallet.setEnabled(False)
        self.enter_scroll_container.setEnabled(False)
        self.exit_scroll_container.setEnabled(False)
        self.add_enter_condition_button.setEnabled(False)
        self.add_exit_condition_button.setEnabled(False)

    @asyncSlot()
    async def on_start(self):
        if self.sol_balance.value() < self.buy_size.value():
            self.log_general_message("Warning: Sol balance cant be lower than the buy size!")
            return

        if self.buy_size.value() <= 0:
            self.log_general_message("Warning: Buy size must be greater than 0!")
            return

        if self.sol_balance.value() <= 0:
            self.log_general_message("Warning: Sol balance must be greater than 0!")
            return

        if self.batch_reset_size.value() <= 0:
            self.log_general_message("Warning: Batch reset size must be greater than 0!")
            return

        if not (len(self.enter_conditions) > 0 and len(self.exit_conditions) > 0):
            self.log_general_message("Please define at least one enter and one exit condition before starting.")
            return

        if self.use_imported_wallet.isChecked():
            # Validate RPC URL if provided
            rpc_url_text = self.rpc_url.toPlainText().strip()
            if rpc_url_text:
                # First check format
                if not self.validate_rpc_url():
                    self.log_general_message("Warning: Invalid RPC URL format! Please enter a valid HTTP/HTTPS URL "
                                             "or leave it empty.")
                    return

                # Then test the endpoint connection
                self.log_general_message("Testing RPC endpoint...")
                if not await self.test_rpc_endpoint(rpc_url_text):
                    self.log_general_message("Warning: RPC endpoint is not working or unreachable. "
                                             "Please check the URL or remove it to use the default endpoint.")
                    return

        self.status_label.setText("Status: Connecting...")

        clear_layout(self.report_layout_conditions_info)
        clear_layout(self.report_layout_charts)
        reset_globals()
        self.entering_sol_balance = self.sol_balance.value()
        self.status_label.setText("Status: Running")
        self.disable_interface()
        self.uptime = time.time()
        self.enter_conditions_for_report = copy(self.interpretable_enter_conditions)
        self.exit_conditions_for_report = copy(self.interpretable_exit_conditions)
        self.task = asyncio.create_task(self.run_subscription(self.interpretable_enter_conditions,
                                                              self.interpretable_exit_conditions))

    async def run_subscription(self, enter_conditions, exit_conditions):
        global records_of_current_subbed_tokens
        try:
            self.cfg = SimpleNamespace(sol_balance_widget=self.sol_balance,
                                       max_slippage=self.max_slippage.value(),
                                       buy_size=self.buy_size.value(),
                                       priority_fee=self.priority_fee.value(),
                                       batch_reset_size=self.batch_reset_size.value(),
                                       inactivity_reset_time=self.inactivity_reset_time.value(),
                                       keypair=self.current_keypair,
                                       rpc_url=self.rpc_url.toPlainText()
                                       )
            self.loggers = SimpleNamespace(log_general_message=self.log_general_message,
                                           log_transaction_message=self.log_transaction_message)
            self.log_general_message("Bot initiated successfully!")
            await subscribe(enter_conditions, exit_conditions, self.loggers, self.cfg,
                            self.use_imported_wallet.isChecked())

        except Exception as e:
            print(f"Error: {e}")
            self.status_label.setText("Status: Cancelled")
            self.log_general_message("Operation was cancelled due to an error!")
            self.build_report()
        finally:
            exit_trades(self.cfg, self.use_imported_wallet, self.loggers)
            self.enable_interface()
            self.log_general_message("Operation was stopped!")
            print(records_of_current_subbed_tokens)
            if not (len(self.enter_conditions) > 0 and len(self.exit_conditions) > 0):
                self.status_label.setText("Status: Waiting for conditions")
            else:
                self.status_label.setText("Status: Ready")

    @asyncSlot()
    async def on_stop(self):
        self.stop_button.setEnabled(False)
        if self.task and not self.task.done():
            self.stop_button.setEnabled(False)
            self.task.cancel()
            self.status_label.setText("Status: Cancelling...")
            self.uptime = time.time() - self.uptime
            time.sleep(8) # give some time to properly exit trades that occur during cancellation
            exit_trades(self.cfg, self.use_imported_wallet.isChecked(), self.loggers)
            self.enable_interface()
            if self.use_imported_wallet.isChecked():
                # reset the sol balance because the system might not be able to get it correctly after real trades
                try:
                    self.sol_balance.setValue(get_balance(self.current_keypair))
                except Exception:
                    pass
                self.sol_balance.setEnabled(False)
            self.build_report()

    def save_state(self):
        global strategy_transcript
        global tokens_created_since_start
        global tokens_evaluated_since_start
        global total_trades_record
        global pnl_sum
        global profitable_trades
        global time_in_trade_sum

        self.settings.setValue("sol_balance", self.sol_balance.value())
        self.settings.setValue("max_slippage", self.max_slippage.value())
        self.settings.setValue("priority_fee", self.priority_fee.value())
        self.settings.setValue("buy_size", self.buy_size.value())
        self.settings.setValue("batch_reset_size", self.batch_reset_size.value())
        self.settings.setValue("inactivity_reset_time", self.inactivity_reset_time.value())
        ent_conds = []
        for cond in self.enter_conditions:
            ent_conds.append(cond.condition)
        self.settings.setValue("enter_conditions", ent_conds)
        exit_conds = []
        for cond in self.exit_conditions:
            exit_conds.append(cond.condition)
        self.settings.setValue("exit_conditions", exit_conds)

        # == Report related ==
        self.settings.setValue("uptime", self.uptime)
        self.settings.setValue("pnl_to_report", self.pnl_to_report)
        self.settings.setValue("enter_conditions_for_report", self.enter_conditions_for_report)
        self.settings.setValue("exit_conditions_for_report", self.exit_conditions_for_report)
        # globals
        self.settings.setValue("strategy_transcript", strategy_transcript)
        self.settings.setValue("tokens_created_since_start", tokens_created_since_start)
        self.settings.setValue("tokens_evaluated_since_start", tokens_evaluated_since_start)
        self.settings.setValue("total_trades_record", total_trades_record)
        self.settings.setValue("pnl_sum", round(pnl_sum, 4))
        self.settings.setValue("profitable_trades", profitable_trades)
        self.settings.setValue("time_in_trade_sum", time_in_trade_sum)

    def load_state(self):
        global strategy_transcript
        global tokens_created_since_start
        global tokens_evaluated_since_start
        global total_trades_record
        global pnl_sum
        global profitable_trades
        global time_in_trade_sum
        try:
            self.sol_balance.setValue(float(self.settings.value("sol_balance", 5)))
            self.max_slippage.setValue(float(self.settings.value("max_slippage", 30)))
            self.priority_fee.setValue(float(self.settings.value("priority_fee", 0)))
            self.buy_size.setValue(float(self.settings.value("buy_size", 0.3)))
            self.batch_reset_size.setValue(int(self.settings.value("batch_reset_size", 10)))
            self.inactivity_reset_time.setValue(float(self.settings.value("inactivity_reset_time", 4)))
            for cond in self.settings.value("enter_conditions", []):
                self.add_condition_row(cond, True)
            self.interpretable_enter_conditions = self.settings.value("enter_conditions", [])
            for cond in self.settings.value("exit_conditions", []):
                self.add_condition_row(cond, False)
            self.interpretable_exit_conditions = self.settings.value("exit_conditions", [])

            # == Report related ==
            self.uptime = float(self.settings.value("uptime", 0))
            self.pnl_to_report = float(self.settings.value("pnl_to_report", 0))
            self.enter_conditions_for_report = self.settings.value("enter_conditions_for_report", [])
            self.exit_conditions_for_report = self.settings.value("exit_conditions_for_report", [])
            # globals
            strategy_transcript = self.settings.value("strategy_transcript", dict())
            tokens_created_since_start = int(self.settings.value("tokens_created_since_start", 0))
            tokens_evaluated_since_start = int(self.settings.value("tokens_evaluated_since_start", 0))
            total_trades_record = int(self.settings.value("total_trades_record", 0))
            pnl_sum = float(self.settings.value("pnl_sum", 0))
            profitable_trades = int(self.settings.value("profitable_trades", 0))
            time_in_trade_sum = float(self.settings.value("time_in_trade_sum", 0))
            self.build_report()
        except Exception as e:
            print(e)
            self.reset_to_default_state()
            reset_globals()

    def reset_to_default_state(self):
        self.sol_balance.setValue(5)
        self.max_slippage.setValue(30)
        self.priority_fee.setValue(0)
        self.buy_size.setValue(0.3)
        self.batch_reset_size.setValue(10)
        self.inactivity_reset_time.setValue(4)
        self.use_imported_wallet.setChecked(False)
        for cond in self.enter_conditions:
            cond.remove_self()
        self.interpretable_enter_conditions = []
        for cond in self.exit_conditions:
            cond.remove_self()
        self.interpretable_exit_conditions = []

    def export_state(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export the current strategy",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                state = dict()
                state.setdefault("sol_balance", self.sol_balance.value())
                state.setdefault("max_slippage", self.max_slippage.value())
                state.setdefault("priority_fee", self.priority_fee.value())
                state.setdefault("buy_size", self.buy_size.value())
                state.setdefault("batch_reset_size", self.batch_reset_size.value())
                state.setdefault("inactivity_reset_time", self.inactivity_reset_time.value())
                ent_conds = []
                for cond in self.enter_conditions:
                    ent_conds.append(cond.condition)
                state.setdefault("enter_conditions", ent_conds)
                exit_conds = []
                for cond in self.exit_conditions:
                    exit_conds.append(cond.condition)
                state.setdefault("exit_conditions", exit_conds)

                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=4)
                QMessageBox.information(self, "Export", f"Export completed successfully! \n Saved at {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not export:\n{e}")

    def import_state(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import a strategy",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    self.sol_balance.setValue(float(state.get("sol_balance", 5)))
                    self.max_slippage.setValue(float(state.get("max_slippage", 30)))
                    self.priority_fee.setValue(float(state.get("priority_fee", 0)))
                    self.buy_size.setValue(float(state.get("buy_size", 0.3)))
                    self.batch_reset_size.setValue(int(state.get("batch_reset_size", 10)))
                    self.inactivity_reset_time.setValue(float(state.get("inactivity_reset_time", 4)))
                    for cond in state.get("enter_conditions", []):
                        self.add_condition_row(cond, True)
                    self.interpretable_enter_conditions = state.get("enter_conditions", [])
                    for cond in state.get("exit_conditions", []):
                        self.add_condition_row(cond, False)
                    self.interpretable_exit_conditions = state.get("exit_conditions", [])
                QMessageBox.information(self, "Import", f"Import completed successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not import:\n{e}")

    def closeEvent(self, event):
        self.save_state()
        event.accept()

    def on_keypair_ready(self, keypair):
        """Called when user imports a keypair"""
        if self.current_keypair is None or self.current_keypair != keypair:
            self.current_keypair = keypair
            print(f"Ready to trade with: {keypair.pubkey()}")
        else:
            self.current_keypair = None
            print(f"Cleaned: {keypair.pubkey()}")

    def use_imported_wallet_changed(self, checked: bool):
        if checked:
            if self.status_label.text() == "Status: Running":
                self.log_general_message("Cannot enable wallet usage while bot is running. Please stop the bot first.")
                self.use_imported_wallet.blockSignals(True)
                self.use_imported_wallet.setChecked(False)
                self.use_imported_wallet.blockSignals(False)
                return
            if self.current_keypair is not None:
                try:
                    wallet_balance = get_balance(self.current_keypair)
                    wallet_balance = float(wallet_balance)
                except Exception as e:
                    self.log_general_message(f"Could not fetch wallet balance: {e}")
                    return
                if wallet_balance == 0:
                    self.log_general_message("Warning: Your wallet balance is 0 SOL. Real trading cannot be performed.")
                    self.use_imported_wallet.blockSignals(True)
                    self.use_imported_wallet.setChecked(False)
                    self.use_imported_wallet.blockSignals(False)
                    return
                if self.buy_size.value() >= wallet_balance:
                    self.buy_size.setValue(wallet_balance / 10)
                    self.log_general_message("Buy size should not be larger or equal to the wallet balance. "
                                             "It is now adjusted to fit wallet balance.")
                self.sol_balance.setValue(float(wallet_balance))
                self.sol_balance.setEnabled(False)
                self.buy_sell_logs_label.setText("Buy/Sell Logs (Statistics shown here may be inaccurate when using real trading due to network latency)")
                self.general_logs_label.setText("General Logs (Statistics shown here may be inaccurate when using real trading due to network latency)")

            else:
                self.log_general_message("You should import your wallet first. Go to Wallet tab.")
                self.use_imported_wallet.blockSignals(True)
                self.use_imported_wallet.setChecked(False)
                self.use_imported_wallet.blockSignals(False)
                return
        else:
            self.sol_balance.setEnabled(True)
            self.buy_sell_logs_label.setText("Buy/Sell Logs")
            self.general_logs_label.setText("General Logs")


    def build_report(self):
        global strategy_transcript
        if not len(strategy_transcript) > 0:
            return
        data = []
        for k, v in strategy_transcript.items():
            data.append(v)
        enter_counts = Counter([e[0] for e in data])
        exit_counts = Counter([e[1] for e in data])
        enter_exit_counts = Counter([e for e in data])

        enter_chart = self.build_pie_chart(enter_counts, "Enter Conditions", "Condition")
        exit_chart = self.build_pie_chart(exit_counts, "Exit Conditions", "Condition")
        enter_exit_chart = self.build_pie_chart(enter_exit_counts, "Enter-Exit Combo", "Combo")

        self.report_layout_charts.addWidget(QChartView(enter_chart))
        self.report_layout_charts.addWidget(QChartView(exit_chart))
        self.report_layout_charts.addWidget(QChartView(enter_exit_chart))

        self.display_strategy_results()

    def build_pie_chart(self, counts, title, label):
        series = QPieSeries()
        total_count = 0
        for _, freq in counts.items():
            total_count += freq
        for el, freq in counts.items():
            series.append(f"{label} {el}: {round((freq/total_count)*100)}% ({freq})", freq)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(title)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        return chart

    def display_strategy_results(self):
        global tokens_created_since_start
        global tokens_evaluated_since_start
        global total_trades_record
        global pnl_sum
        global profitable_trades
        global time_in_trade_sum

        if self.use_imported_wallet.isChecked():
            self.report_layout_conditions_info.addWidget(QLabel("<b>Note:</b> Statistics shown here may be inaccurate "
                                                                "when using real trading due to network latency."))


        title_label = QLabel("Conditions")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 8px;")
        self.report_layout_conditions_info.addWidget(title_label)

        enter_conditions_group = QGroupBox()
        enter_conditions_group.setTitle("Enter Conditions")
        enter_group_layout = QVBoxLayout(enter_conditions_group)

        exit_conditions_group = QGroupBox()
        exit_conditions_group.setTitle("Exit Conditions")
        exit_group_layout = QVBoxLayout(exit_conditions_group)

        for cond in self.enter_conditions_for_report:
            formatted_cond = ""
            for sub_cond in cond:
                formatted_cond += "\n" + str(sub_cond[0]) + " " + str(sub_cond[1]) + " " + str(sub_cond[2])
            cond_label = QLabel(f"Condition {self.enter_conditions_for_report.index(cond) + 1}:{formatted_cond}")
            cond_label.setStyleSheet("font-size: 14px; margin: 4px;")
            enter_group_layout.addWidget(cond_label)
            enter_group_layout.addWidget(QLabel("<hr>"))

        for cond in self.exit_conditions_for_report:
            formatted_cond = ""
            for sub_cond in cond:
                formatted_cond += "\n" + str(sub_cond[0]) + " " + str(sub_cond[1]) + " " + str(sub_cond[2])
            cond_label = QLabel(f"Condition {self.exit_conditions_for_report.index(cond) + 1}:{formatted_cond}")
            cond_label.setStyleSheet("font-size: 14px; margin: 4px;")
            exit_group_layout.addWidget(cond_label)
            exit_group_layout.addWidget(QLabel("<hr>"))

        self.report_layout_conditions_info.addWidget(enter_conditions_group)
        self.report_layout_conditions_info.addWidget(exit_conditions_group)

        statistics = QLabel("Statistics")
        statistics.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 8px;")
        self.report_layout_conditions_info.addWidget(statistics)

        if self.entering_sol_balance is not None:
            pnl = ((self.sol_balance.value() - self.entering_sol_balance) / self.entering_sol_balance) * 100
        else:
            pnl = self.pnl_to_report  # previous recorded pnl (we are loading the previous report)

        pnl_str = f"{pnl:+.2f}%"
        self.add_report_label(f"PnL: <b>{pnl_str}</b>")
        self.pnl_to_report = pnl


        self.add_report_label(f"Bot uptime: <b>{format_duration(self.uptime)}</b>")
        self.add_report_label(f"No. of tokens created since bot initiation: <b>{tokens_created_since_start}</b>")
        self.add_report_label(f"No. of tokens evaluated: <b>{tokens_evaluated_since_start}</b>")
        self.add_report_label(f"No. of trades taken: <b>{total_trades_record}</b>")
        self.add_report_label(f"No. of profitable trades: <b>{profitable_trades}</b>")
        self.add_report_label(f"Average PnL per trade: <b>{round(pnl_sum/total_trades_record, 2)}%</b>")
        self.add_report_label(f"Average time in trade: <b>{format_duration(time_in_trade_sum/total_trades_record)}</b>")

        self.report_layout_conditions_info.addStretch()

    def add_report_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 14px; margin: 4px;")
        self.report_layout_conditions_info.addWidget(label)


# --- App entry point ---
def lets_do_this():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.resize(1600, 840)
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    lets_do_this()
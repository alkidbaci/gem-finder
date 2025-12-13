# 🎯 Sniper Bot Instructions

Sniper bot is implemented to make it possible for you to apply your
sniper strategy to newly created _pump.fun_ tokens. You first start by specifying some
general input parameters and then the enter and exit conditions. Let's go
through each of them. Focus of this bot is not in long term holdings, but quick in-and-outs for profits on
newly created tokens. If you find a good strategy those profits can compound quickly. I have seen it happen and
since you are here, maybe you did too :).

> Remember, this is paper trading bot, and we want to simulate a trade
> as closely as possible to a real one.

## ⚙️ General Input Parameters

- **Sol Balance**: The amount of SOL you want to use for the sniper bot. This
    will be updated on each trade. The field becomes read-only after you start the bot.
- **Slippage**: Maximum allowance in percentage for the difference between the price you requested for a trade and the
    price at which the trade is actually executed.
- **Buy Size**: The amount of sol you want to use for your trades. We recommend a
    small value compared to the market cap since a larger value would make a significant
    difference in a real world scenario.
- **Priority fee**: The priority fee in SOL you want to pay for each transaction.
    Higher priority fees will make your transaction be processed faster.
- **Token batch before reset**: The number of tokens you want to subscribe at a given time.
    Unless there is no token being trade from the current batch and the batch reset size is reached
    a reset will occur, i.e. old tokens will be unsubscribed and entry conditions will be evaluated on new ones.
    Keep in mind that while tokens in the current batch are being traded and the token batch size has reached his limit,
    no new token is being evaluated although new tokens are created every second. That means that you may miss a
    potential trade. It's necessary to find a tradeoff value for this parameter.
- **Time of inactivity before selling**: The time in seconds that the bot will wait before selling a token
    that has been bought and is not being traded anymore. Some tokens may be slow and this is considered an exit strategy.
    If you don't want this to happen, just set a high value.
- **Use Imported Wallet**: If this option is checked, the bot will use your imported wallet to make trades. You can
    import your wallet in the Wallet tab.

## 📈 Entering and Exiting Conditions
- **Enter Condition**: This is a condition that will be evaluated on each token in the batch.
    If the condition is met, the bot will buy the token. The condition is specified by clicking the
    "Add" button on the right side of the field. A window will pop up where you
    can enter the sub-conditions. A sub-condition is made of 3 fields: the property to evaluate,
    the operator to apply and the value to compare against. Let's go through each property:
    - _total trades_: The total number of trades that have been made on the token.
    - _transaction/sec_: The number of transactions per second that have been made on the token.
    - _buys_: The number of buy transactions that have been made on the token.
    - _sells_: The number of sell transactions that have been made on the token.
    - _mcap_: The market cap of the token.
    - _mcap slope_: Used to evaluate the trend slope (units per second) based on the market cap.
    - _trend strength_: The strength of the trend based on the market cap.
    - _avg buy volume_: The average buy volume of the token.

- **Exit Conditions**: These conditions are evaluated on each token that has been bought.
    If the condition is met, the bot will sell the token. You can set conditions similar to
    the enter conditions. The properties are similar to those in
    the enter conditions, but you can also use:
    - _PnL (in %)_: The profit and loss percentage of the token since it was bought.
    - _time elapsed_: The time in seconds that has elapsed since the token was bought.

    There are 2 special exit condition with the following codes:
    - Condition 101: A token is sold after **x** seconds of inactivity. This time is defined in general inputs.
    - Condition 100: If you stop the bot and there are tokens yet not sold, they will be sold automatically.


## 💡 Strategy Example
Let's take the input parameters one by one and discuss what would
be the optimal values for a sniper strategy.

Starting with the general input parameters:

- **Sol Balance**: It's true that we are paper trading here and we don't
    risk real money, but it's still a good practice to set a realistic
    balance. A value between 5 and 20 SOL would be a good starting point.
- **Slippage**: In newly created tokens, the liquidity is usually low,
    and the price may vary significantly between the time you send
    the transaction and the time it is executed. If you actually want your trades to make it through, you need to
    set a high slippage value.
- **Buy Size**: Since we are paper trading, we don't want to use a large
    buy size because your trade is not reflected in the market which would otherwise
    potentially affect the price and other traders actions. A value between 0.1 and 0.3 SOL is recommended.
- **Priority fee**: Higher priority fees will make your transaction
    be processed faster. In a sniper strategy, speed is of essence.
    A value between 0 and 0.005 SOL would be a good starting point.
- **Token batch before reset**: The idea is to not overload the webservice.
    Not only it will slow down the processing, but it may also lead to being banned from _pump.fun_ api endpoints.
    A value of 10 would be a good to go value.
    This means that the bot will subscribe to 10 tokens at a time and evaluate
    the entry conditions on them. If no token is bought from the current batch
    and the batch reset size is reached, a reset will occur meaning that the old tokens
    will be unsubscribed and new ones will the system will allow for new ones to be subscribed.
- **Time of inactivity before selling**: Some tokens may be slow, and
    you may want to sell it after absence of trades using a time limit.
    This value highly depends on your strategy. For example if you are
    taking in average 10-second trades, you may want to set this value to 4 seconds.
    Feel free to adjust this value to fit your strategy.
- **Use Imported Wallet**: If you want to make trades using your own wallet,
    check this option. Make sure that your wallet has enough SOL balance
    to cover the trades and the transaction fees.

Make sure to set sensible values, for example sol balance should be greater than 0. The
program has some basic input validation, but it is not bulletproof, and you don't want it
to crash on you.

Ok that's it for the general parameters.
Now let's move to the real deal, the enter and exit conditions.
The example we are going to show is completely arbitrary and is just
to give you an idea of how you can combine your sub-conditions
to form a condition and your conditions to form a strategy.

### Enter Conditions

**Enter condition 1:**
- total_trades > 7
- tx_sec > 2
- buys_sells_ratio > 1
- avg_buy_volume > 0.3

**Enter condition 2:**
- buys > 5
- avg_buy_volume > 1

**Enter condition 3:**
- slope > 0.4
- trend_strength > 0.7

### Exit Conditions

**Exit condition 1:** pnl(%) > 75 | time_elapsed > 6

**Exit condition 2:** pnl(%) < 75 | pnl(%) > 0.3 | time_elapsed > 18 | tx_sec < 3

**Exit condition 3:** pnl(%) < -10 | time_elapsed > 15

**Exit condition 4:** pnl(%) < -25

## 🚀 Starting and Stopping the Bot

Once you have set your parameters and conditions, click on the "Start" button
to start the bot. You can stop the bot at any time by clicking on the "Stop" button.

Note: When you stop the bot, each token that you had bought in and was not sold, will be sold at the current price
of the respective token.

Happy sniping!


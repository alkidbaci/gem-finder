# Gem-Finder — Strategy Builder & Paper-Trading Sniper Bot for Solana Tokens

**Gem-Finder** is a desktop application designed for creating, testing, and refining **sniping strategies** 
for newly launched Solana tokens (memecoins). <br>
Built with **Python + PyQt**, it provides a smooth, GUI-based workflow for exploring trading 
logic without needing to write code while still offering deep customization options for developers.

Gem-Finder is built with **educational and research purposes** in mind.<br>
It performs **paper-trading simulations by default**, using a custom engine that mimics real Solana market 
behavior as closely as possible.

For advanced users who’ve validated a profitable strategy, the tool can also be configured to perform **real 
on-chain trades**. Use this responsibly and always test thoroughly before risking funds.


![Main Screen](/images/window_main.png)

![Report Screen](/images/window_report.png)

![Instruction Screen](/images/window_instructions.png)

---

## Key Features
- User-friendly system native UI
- Craft a strategy by defining multiple entry/exit conditions
- Export and import of strategies possible.
- Realistic paper-trading simulator
- Real-time token monitoring
- Customizable logic
- Optional on-chain trading support
- Report & statistics dashboard for strategy performance

---

## Installation

### Pre-bundled app
You can install the app directly from the release files: **Releases** > **gem-finder 1.0** > **gem-finder-1.0** (under '_Assets_')

### From Source

You can also install it from source and run locally and/or bundle it yourself.

#### Install Python ≥ 3.11. 

Find the installer in the official
[python.org](https://www.python.org/) website, run the executable, and make sure to check
"Add python.exe to PATH" during installation. After clicking "Install", you can verify the installation by opening the
command prompt and typing `python --version`. 

#### Clone the repository

Simply download the project: **Code** > **Download ZIP** and extract it into a directory of your choice.

#### Install required dependence 

Open your command terminal and go to the directory of the just extracted project:
```shell
cd path/to/gem-finder
```

Create a virtual environment:
```shell
python -m venv venv
```

Activate the virtual environment:
```shell
source venv/bin/activate # for Unix and macOS
.\venv\Scripts\activate  # for Windows
```

Install dependencies:

```shell
pip install -r requirements.txt
```

#### Launching

Now you either bundle the project files into an executable file that you can run by double-clicking, 
or you can run the project by the python interpreter.

If you want to run it via the python interpreter:
```shell
python -m gem-finder.py
```

If you want to bundle it:
```shell
pyinstaller --windowed --onefile  --add-data "instructions.md;."  --add-data "images;images" gem-finder.py --icon images/tourmaline.png
```
After this command you will find your executable under `your-project-root/dist/`.

---

## Development
In case you spend time on building over it please feel free to open a PR.

---

## More scripts
You will also find a copy trading bot which is not yet integrated with Gem-Finder but you can use it as following:
```shell
python -m copy_trade.py 
```
This script accepts the following arguments:
- `--wallet_to_copy`* &rarr; Wallet address you wish to copy trades from
- `--public_key`* &rarr; Public key of your wallet
- `--private_key`* &rarr; Private key of your wallet
- `--amount` &rarr; Amount you wish to buy per trade (in SOL)
- `--slippage` &rarr; Slippage in percentage, e.g. 20 (means 20%)
- `--priority_fee` &rarr; Priority fee in SOL

---

## Disclaimer

Gem-Finder is provided for **educational and research purposes** only and comes **without any warranty**.<br>
Nothing in this software constitutes financial advice or a recommendation to trade cryptocurrencies.
Using this tool for live trading may result in monetary loss.
You are solely responsible for any actions taken using it, including strategy decisions, private key management, and real-money transactions.
The authors and contributors are not liable for any financial losses, errors, or damages resulting from the use of this software.

---

## Contact
In case of any question or suggestion please open an issue here on GitHub or by contacting me at [alkid1baci@gmail.com](mailto:alkid1baci@gmail.com).


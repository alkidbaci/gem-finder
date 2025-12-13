import time

import requests
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from solders.commitment_config import CommitmentLevel
from solders.rpc.requests import SendVersionedTransaction
from solders.rpc.config import RpcSendTransactionConfig

start = time.time()
public_key = "YOUR_PUBLIC_KEY"
private_key = "YOUR_PRIVATE_KEY"
mint = "enter_here_the_contract_address_of_the_token_you_want_to_trade"

response = requests.post(url="https://pumpportal.fun/api/trade-local", data={
    "publicKey": public_key,
    "action": "sell",              # "buy" or "sell"
    "mint": mint,      # contract address of the token you want to trade
    "amount": "100%",             # amount of SOL or tokens to trade
    "denominatedInSol": "false",  # "true" if amount is amount of SOL, "false" if amount is number of tokens
    "slippage": 20,               # percent slippage allowed
    "priorityFee": 0,         # amount to use as priority fee
    "pool": "auto"                # exchange to trade on. "pump", "raydium", "pump-amm" or "auto"
})

keypair = Keypair.from_base58_string(private_key)
tx = VersionedTransaction(VersionedTransaction.from_bytes(response.content).message, [keypair])

commitment = CommitmentLevel.Confirmed
config = RpcSendTransactionConfig(preflight_commitment=commitment)
txPayload = SendVersionedTransaction(tx, config)

response = requests.post(
    url="https://api.mainnet-beta.solana.com/",  # Your RPC Endpoint here
    headers={"Content-Type": "application/json"},
    data=SendVersionedTransaction(tx, config).to_json()
)
txSignature = response.json()['result']
print(f'Transaction: https://solscan.io/tx/{txSignature}')
end = time.time() - start
print(end)

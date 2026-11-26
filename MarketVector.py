import json
import random
import time
from pathlib import Path

from jito_searcher_client import get_searcher_client
from jito_searcher_client.convert import versioned_tx_to_protobuf_packet
from jito_searcher_client.generated.bundle_pb2 import Bundle
from jito_searcher_client.generated.searcher_pb2 import (
    GetTipAccountsRequest,
    SendBundleRequest,
)
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction

RPC_URL = "https://api.mainnet-beta.solana.com"
BLOCK_ENGINE = "frankfurt.mainnet.block-engine.jito.wtf"
KEYPAIR_PATH = Path.home() / ".config" / "solana" / "id.json"
TIP_LAMPORTS = 1000
NUM_BUNDLES = 5
CHECKS = 20

rpc = Client(RPC_URL)


def get_wallet():
    with open(KEYPAIR_PATH) as f:
        secret = json.load(f)
    return Keypair.from_bytes(bytes(secret))


def build_tip_tx(kp, tip_account):
    blockhash = rpc.get_latest_blockhash().value.blockhash
    ix = transfer(
        TransferParams(
            from_pubkey=kp.pubkey(),
            to_pubkey=Pubkey.from_string(tip_account),
            lamports=TIP_LAMPORTS,
        )
    )
    msg = MessageV0.try_compile(kp.pubkey(), [ix], [], blockhash)
    return VersionedTransaction(msg, [kp])


def send_bundle(client, tx):
    packet = versioned_tx_to_protobuf_packet(tx)
    req = SendBundleRequest(bundle=Bundle(packets=[packet]))
    resp = client.SendBundle(req)
    return resp.uuid


def did_it_land(sig):
    for _ in range(CHECKS):
        time.sleep(3)
        res = rpc.get_signature_statuses([sig])
        status = res.value[0]
        if status is None:
            continue
        if status.err is None and str(status.confirmation_status) in (
            "TransactionConfirmationStatus.Confirmed",
            "TransactionConfirmationStatus.Finalized",
        ):
            return True
    return False


kp = get_wallet()
client = get_searcher_client(BLOCK_ENGINE, kp)
results = []


def run_once(i):
    tip_accounts = client.GetTipAccounts(GetTipAccountsRequest()).accounts
    tx = build_tip_tx(kp, random.choice(tip_accounts))
    uuid = send_bundle(client, tx)
    print(f"[{i}] -> {uuid}")
    landed = did_it_land(tx.signatures[0])
    print("landed" if landed else "not landed")
    results.append(landed)


if __name__ == "__main__":
    for i in range(NUM_BUNDLES):
        print("test", i + 1)
        try:
            run_once(i)
        except Exception as e:
            print("error", e)
            results.append(False)
    ok = sum(results)
    print("rate:", ok, "/", len(results))
    print(int(ok / len(results) * 100))

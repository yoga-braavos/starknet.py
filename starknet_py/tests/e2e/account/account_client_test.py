import os.path
from pathlib import Path
import pytest

from starknet_py.contract import Contract
from starknet_py.net import AccountClient
from starknet_py.net.models import StarknetChainId
from starknet_py.tests.e2e.utils import DEVNET_ADDRESS

directory = os.path.dirname(__file__)
map_source_code = Path(directory, "map.cairo").read_text("utf-8")


@pytest.mark.asyncio
async def test_deploy_account_contract_and_sign_tx():
    acc_client = await AccountClient.create_account(
        net=DEVNET_ADDRESS, chain=StarknetChainId.TESTNET
    )

    map_contract = await Contract.deploy(
        client=acc_client, compilation_source=map_source_code
    )
    k, v = 13, 4324
    await map_contract.functions["put"].invoke(k, v)
    (resp,) = await map_contract.functions["get"].call(k)

    assert resp == v
# pylint: disable=too-many-arguments
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from starknet_py.hash.selector import get_selector_from_name
from starknet_py.hash.storage import get_storage_var_address
from starknet_py.net.client_models import (
    Call,
    DeclareTransaction,
    DeployAccountTransaction,
    GatewayBlock,
    InvokeTransaction,
    L1HandlerTransaction,
    TransactionReceipt,
    TransactionStatus,
)
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.udc_deployer.deployer import Deployer
from starknet_py.tests.e2e.fixtures.constants import MAX_FEE
from starknet_py.tests.e2e.fixtures.misc import read_contract
from starknet_py.transaction_exceptions import (
    TransactionNotReceivedError,
    TransactionRejectedError,
)


@pytest.mark.asyncio
async def test_get_declare_transaction(
    client, declare_transaction_hash, class_hash, gateway_account
):
    transaction = await client.get_transaction(declare_transaction_hash)

    assert isinstance(transaction, DeclareTransaction)
    assert transaction.class_hash == class_hash
    assert transaction.hash == declare_transaction_hash
    assert transaction.sender_address == gateway_account.address


@pytest.mark.asyncio
async def test_get_invoke_transaction(
    client,
    invoke_transaction_hash,
):
    transaction = await client.get_transaction(invoke_transaction_hash)

    assert isinstance(transaction, InvokeTransaction)
    assert any(data == 1234 for data in transaction.calldata)
    assert transaction.hash == invoke_transaction_hash


@pytest.mark.asyncio
async def test_get_deploy_account_transaction(client, deploy_account_transaction_hash):
    transaction = await client.get_transaction(deploy_account_transaction_hash)

    assert isinstance(transaction, DeployAccountTransaction)
    assert transaction.hash == deploy_account_transaction_hash
    assert len(transaction.signature) > 0
    assert transaction.nonce == 0


@pytest.mark.asyncio
async def test_get_transaction_raises_on_not_received(client):
    with pytest.raises(
        TransactionNotReceivedError, match="Transaction was not received on Starknet."
    ):
        await client.get_transaction(tx_hash=0x9999)


@pytest.mark.asyncio
async def test_get_block_by_hash(
    client,
    block_with_declare_hash,
    block_with_declare_number,
):
    block = await client.get_block(block_hash=block_with_declare_hash)

    assert block.block_number == block_with_declare_number
    assert block.block_hash == block_with_declare_hash
    assert len(block.transactions) != 0

    if isinstance(block, GatewayBlock):
        assert block.gas_price > 0


@pytest.mark.asyncio
async def test_get_block_by_number(
    client,
    block_with_declare_number,
    block_with_declare_hash,
):
    block = await client.get_block(block_number=block_with_declare_number)

    assert block.block_number == block_with_declare_number
    assert block.block_hash == block_with_declare_hash
    assert len(block.transactions) != 0

    if isinstance(block, GatewayBlock):
        assert block.gas_price > 0


@pytest.mark.asyncio
async def test_get_storage_at(client, contract_address):
    storage = await client.get_storage_at(
        contract_address=contract_address,
        key=get_storage_var_address("balance"),
        block_hash="latest",
    )

    assert storage == 1234


@pytest.mark.asyncio
async def test_get_transaction_receipt(
    client, invoke_transaction_hash, block_with_invoke_number
):
    receipt = await client.get_transaction_receipt(tx_hash=invoke_transaction_hash)

    assert receipt.hash == invoke_transaction_hash
    assert receipt.block_number == block_with_invoke_number


@pytest.mark.asyncio
async def test_estimate_fee_invoke(account, contract_address):
    invoke_tx = await account.sign_invoke_transaction(
        calls=Call(
            to_addr=contract_address,
            selector=get_selector_from_name("increase_balance"),
            calldata=[123],
        ),
        max_fee=MAX_FEE,
    )
    invoke_tx = await account.sign_for_fee_estimate(invoke_tx)
    estimate_fee = await account.client.estimate_fee(tx=invoke_tx)

    assert isinstance(estimate_fee.overall_fee, int)
    assert estimate_fee.overall_fee > 0


@pytest.mark.asyncio
async def test_estimate_fee_declare(account):
    declare_tx = await account.sign_declare_transaction(
        compiled_contract=read_contract("map_compiled.json"), max_fee=MAX_FEE
    )
    declare_tx = await account.sign_for_fee_estimate(declare_tx)
    estimate_fee = await account.client.estimate_fee(tx=declare_tx)

    assert isinstance(estimate_fee.overall_fee, int)
    assert estimate_fee.overall_fee > 0


@pytest.mark.asyncio
async def test_estimate_fee_deploy_account(client, deploy_account_transaction):
    estimate_fee = await client.estimate_fee(tx=deploy_account_transaction)

    assert isinstance(estimate_fee.overall_fee, int)
    assert estimate_fee.overall_fee > 0


@pytest.mark.asyncio
async def test_call_contract(client, contract_address):
    call = Call(
        to_addr=contract_address,
        selector=get_selector_from_name("get_balance"),
        calldata=[],
    )

    result = await client.call_contract(call, block_number="latest")

    assert result == [1234]


@pytest.mark.asyncio
async def test_add_transaction(map_contract, client, account):
    prepared_function_call = map_contract.functions["put"].prepare(key=73, value=12)
    signed_invoke = await account.sign_invoke_transaction(
        calls=prepared_function_call, max_fee=MAX_FEE
    )

    result = await client.send_transaction(signed_invoke)
    await client.wait_for_tx(result.transaction_hash)
    transaction_receipt = await client.get_transaction_receipt(result.transaction_hash)

    assert transaction_receipt.status != TransactionStatus.NOT_RECEIVED


@pytest.mark.asyncio
async def test_get_class_hash_at(client, contract_address, class_hash):
    received_class_hash = await client.get_class_hash_at(
        contract_address=contract_address, block_hash="latest"
    )
    assert received_class_hash == class_hash


@pytest.mark.asyncio
async def test_get_class_by_hash(client, class_hash):
    contract_class = await client.get_class_by_hash(class_hash=class_hash)
    assert contract_class.program != ""
    assert contract_class.entry_points_by_type is not None
    assert contract_class.abi is not None


@pytest.mark.asyncio
async def test_wait_for_tx_accepted(gateway_client):
    with patch(
        "starknet_py.net.gateway_client.GatewayClient.get_transaction_receipt",
        AsyncMock(),
    ) as mocked_receipt:
        mocked_receipt.return_value = TransactionReceipt(
            hash=0x1, status=TransactionStatus.ACCEPTED_ON_L2, block_number=1
        )

        block_number, tx_status = await gateway_client.wait_for_tx(tx_hash=0x1)
        assert block_number == 1
        assert tx_status == TransactionStatus.ACCEPTED_ON_L2


@pytest.mark.asyncio
async def test_wait_for_tx_pending(gateway_client):
    with patch(
        "starknet_py.net.gateway_client.GatewayClient.get_transaction_receipt",
        AsyncMock(),
    ) as mocked_receipt:
        mocked_receipt.return_value = TransactionReceipt(
            hash=0x1, status=TransactionStatus.PENDING, block_number=1
        )

        block_number, tx_status = await gateway_client.wait_for_tx(tx_hash=0x1)
        assert block_number == 1
        assert tx_status == TransactionStatus.PENDING


@pytest.mark.parametrize(
    "status, exception, exc_message",
    (
        (
            TransactionStatus.REJECTED,
            TransactionRejectedError,
            "Unknown Starknet error",
        ),
        (
            TransactionStatus.NOT_RECEIVED,
            TransactionNotReceivedError,
            "Transaction not received",
        ),
    ),
)
@pytest.mark.asyncio
async def test_wait_for_tx_rejected(status, exception, exc_message, gateway_client):
    with patch(
        "starknet_py.net.gateway_client.GatewayClient.get_transaction_receipt",
        AsyncMock(),
    ) as mocked_receipt:
        mocked_receipt.return_value = TransactionReceipt(
            hash=0x1, status=status, block_number=1, rejection_reason=exc_message
        )

        with pytest.raises(exception) as err:
            await gateway_client.wait_for_tx(tx_hash=0x1)

        assert exc_message in err.value.message


@pytest.mark.asyncio
async def test_wait_for_tx_cancelled(gateway_client):
    with patch(
        "starknet_py.net.gateway_client.GatewayClient.get_transaction_receipt",
        AsyncMock(),
    ) as mocked_receipt:
        mocked_receipt.return_value = TransactionReceipt(
            hash=0x1, status=TransactionStatus.PENDING, block_number=1
        )

        task = asyncio.create_task(
            gateway_client.wait_for_tx(tx_hash=0x1, wait_for_accept=True)
        )
        await asyncio.sleep(1)
        task.cancel()

        with pytest.raises(TransactionNotReceivedError):
            await task


@pytest.mark.asyncio
async def test_declare_contract(map_compiled_contract, account):
    declare_tx = await account.sign_declare_transaction(
        compiled_contract=map_compiled_contract, max_fee=MAX_FEE
    )

    client = account.client
    result = await client.declare(declare_tx)
    await client.wait_for_tx(result.transaction_hash)
    transaction_receipt = await client.get_transaction_receipt(result.transaction_hash)

    assert transaction_receipt.status != TransactionStatus.NOT_RECEIVED
    assert transaction_receipt.hash
    assert 0 < transaction_receipt.actual_fee <= MAX_FEE


@pytest.mark.asyncio
async def test_custom_session(map_contract, network):
    # We must access protected `feeder_gateway_client` to test session
    # pylint: disable=protected-access

    session = ClientSession()

    tx_hash = (
        await (
            await map_contract.functions["put"].invoke(
                key=10, value=20, max_fee=MAX_FEE
            )
        ).wait_for_acceptance()
    ).hash

    gateway_client1 = GatewayClient(net=network, session=session)
    gateway_client2 = GatewayClient(net=network, session=session)

    assert gateway_client1._feeder_gateway_client.session is not None
    assert gateway_client1._feeder_gateway_client.session == session
    assert gateway_client1._feeder_gateway_client.session.closed is False
    assert gateway_client2._feeder_gateway_client.session is not None
    assert gateway_client2._feeder_gateway_client.session == session
    assert gateway_client2._feeder_gateway_client.session.closed is False

    gateway1_response = await gateway_client1.get_transaction_receipt(tx_hash=tx_hash)
    gateway2_response = await gateway_client2.get_transaction_receipt(tx_hash=tx_hash)
    assert gateway1_response == gateway2_response

    assert gateway_client1._feeder_gateway_client.session.closed is False
    assert gateway_client2._feeder_gateway_client.session.closed is False

    await session.close()

    assert gateway_client1._feeder_gateway_client.session.closed is True
    assert gateway_client2._feeder_gateway_client.session.closed is True


@pytest.mark.asyncio
async def test_get_l1_handler_transaction(client):
    with patch(
        "starknet_py.net.http_client.GatewayHttpClient.call", AsyncMock()
    ) as mocked_transaction_call_gateway, patch(
        "starknet_py.net.http_client.RpcHttpClient.call", AsyncMock()
    ) as mocked_transaction_call_rpc:
        return_value = {
            "status": "ACCEPTED_ON_L1",
            "block_hash": "0x38ce7678420eaff5cd62597643ca515d0887579a8be69563067fe79a624592b",
            "block_number": 370459,
            "transaction_index": 9,
            "transaction": {
                "version": "0x0",
                "contract_address": "0x278f24c3e74cbf7a375ec099df306289beb0605a346277d200b791a7f811a19",
                "entry_point_selector": "0x2d757788a8d8d6f21d1cd40bce38a8222d70654214e96ff95d8086e684fbee5",
                "nonce": "0x34c20",
                "calldata": [
                    "0xd8beaa22894cd33f24075459cfba287a10a104e4",
                    "0x3f9c67ef1d31e24b386184b4ede63a869c4659de093ef437ee235cae4daf2be",
                    "0x3635c9adc5dea00000",
                    "0x0",
                    "0x7cb4539b69a2371f75d21160026b76a7a7c1cacb",
                ],
                "transaction_hash": "0x7e1ed66dbccf915857c6367fc641c24292c063e54a5dd55947c2d958d94e1a9",
                "type": "L1_HANDLER",
            },
        }
        mocked_transaction_call_gateway.return_value = return_value
        mocked_transaction_call_rpc.return_value = return_value["transaction"]

        transaction = await client.get_transaction(tx_hash=0x1)

        assert isinstance(transaction, L1HandlerTransaction)
        assert transaction.nonce is not None
        assert transaction.nonce == 0x34C20


@pytest.mark.run_on_devnet
@pytest.mark.asyncio
async def test_state_update_declared_contract_hashes(
    client,
    block_with_declare_number,
    class_hash,
):
    state_update = await client.get_state_update(block_number=block_with_declare_number)

    if isinstance(client, FullNodeClient):
        assert class_hash in state_update.state_diff.declared_contract_hashes
    else:
        assert class_hash in state_update.state_diff.deprecated_declared_contract_hashes


@pytest.mark.run_on_devnet
@pytest.mark.asyncio
async def test_state_update_storage_diffs(
    client,
    map_contract,
):
    resp = await map_contract.functions["put"].invoke(key=10, value=20, max_fee=MAX_FEE)
    await resp.wait_for_acceptance()

    state_update = await client.get_state_update()

    assert len(state_update.state_diff.storage_diffs) != 0


@pytest.mark.run_on_devnet
@pytest.mark.asyncio
async def test_state_update_deployed_contracts(
    class_hash,
    account,
):
    # setup
    deployer = Deployer()
    contract_deployment = deployer.create_deployment_call(class_hash=class_hash)
    deploy_invoke_tx = await account.sign_invoke_transaction(
        contract_deployment.call, max_fee=MAX_FEE
    )
    resp = await account.client.send_transaction(deploy_invoke_tx)
    await account.client.wait_for_tx(resp.transaction_hash)

    # test
    state_update = await account.client.get_state_update()

    assert len(state_update.state_diff.deployed_contracts) != 0

from typing import Tuple

import pytest
from starkware.starknet.core.os.transaction_hash.transaction_hash import (
    calculate_declare_transaction_hash as sw_calculate_declare_transaction_hash,
)
from starkware.starknet.core.os.transaction_hash.transaction_hash import (
    calculate_deprecated_declare_transaction_hash,
)
from starkware.starknet.services.api.contract_class.contract_class import (
    ContractClass,
    DeprecatedCompiledClass,
)

from starknet_py.common import create_compiled_contract, create_sierra_compiled_contract
from starknet_py.hash.transaction import (
    TransactionHashPrefix,
    compute_declare_transaction_hash,
    compute_declare_v2_transaction_hash,
    compute_deploy_account_transaction_hash,
    compute_transaction_hash,
)
from starknet_py.net.models import StarknetChainId
from starknet_py.net.schemas.gateway import SierraCompiledContractSchema
from starknet_py.tests.e2e.fixtures.misc import read_contract


@pytest.mark.parametrize(
    "data, calculated_hash",
    (
        (
            [TransactionHashPrefix.INVOKE, 2, 3, 4, [5], 6, 7, [8]],
            1176541524183318710439453346174486593835028723304878846501762065493748312757,
        ),
        (
            [TransactionHashPrefix.L1_HANDLER, 15, 39, 74, [74], 39, 15, [28]],
            1226653506056503634668815848352741482067480791322607584496401451909331743178,
        ),
    ),
)
def test_compute_transaction_hash(data, calculated_hash):
    assert compute_transaction_hash(*data) == calculated_hash


@pytest.mark.parametrize(
    "data, calculated_hash",
    (
        (
            [2, 3, 4, [5], 6, 7, 8, 9],
            3319639522829811634906602140344071246050815451799261765214603967516640029516,
        ),
        (
            [12, 23, 34, [45], 56, 67, 78, 89],
            1704331554042454954615983716430494560849200211800542196314933915246556687567,
        ),
    ),
)
def test_compute_deploy_account_transaction_hash(data, calculated_hash):
    assert compute_deploy_account_transaction_hash(*data) == calculated_hash


@pytest.mark.parametrize(
    "contract_json, data",
    (
        ("map_compiled.json", [3, 4, 5, 1, 7]),
        ("balance_compiled.json", [23, 24, 25, 26, 27]),
    ),
)
def test_compute_declare_transaction_hash(contract_json, data):
    contract = read_contract(contract_json)
    compiled_contract = create_compiled_contract(compiled_contract=contract)

    declare_hash = compute_declare_transaction_hash(compiled_contract, *data)

    sw_declare_hash = calculate_deprecated_declare_transaction_hash(
        DeprecatedCompiledClass.loads(contract), *data
    )

    assert declare_hash == sw_declare_hash


def test_compute_declare_v2_transaction_hash(
    sierra_minimal_compiled_contract_and_class_hash: Tuple[str, int],
):
    contract, compiled_class_hash = sierra_minimal_compiled_contract_and_class_hash
    compiled_contract = create_sierra_compiled_contract(contract)

    declare_hash = compute_declare_v2_transaction_hash(
        contract_class=compiled_contract,
        compiled_class_hash=compiled_class_hash,
        chain_id=StarknetChainId.TESTNET.value,
        sender_address=0x1,
        max_fee=2000,
        version=2,
        nonce=23,
    )

    serialized_compiled_contract = SierraCompiledContractSchema().dumps(
        compiled_contract
    )
    contract_class = ContractClass.loads(serialized_compiled_contract)

    sw_declare_hash = sw_calculate_declare_transaction_hash(
        contract_class=contract_class,
        compiled_class_hash=compiled_class_hash,
        chain_id=StarknetChainId.TESTNET.value,
        sender_address=0x1,
        max_fee=2000,
        version=2,
        nonce=23,
    )

    assert declare_hash == sw_declare_hash

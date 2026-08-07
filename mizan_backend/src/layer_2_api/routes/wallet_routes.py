"""Layer 2 — Digital Wallet HTTP routes.

Routes are intentionally thin: they parse/validate transport-level
input, delegate to `WalletController`, and return its result as the
appropriate response schema. All business logic and domain-exception
translation lives in `WalletController` — this module must never
contain either.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..controllers.wallet_controller import WalletController
from ..schemas.wallet_schemas import (
    DepositRequest,
    ErrorResponse,
    TransactionResponse,
    TransferRequest,
    TransferResponse,
    WalletBalanceResponse,
    WithdrawRequest,
)

router = APIRouter(prefix="/wallet", tags=["wallet"])

#: Every error code `WalletController` can raise, documented once and
#: reused across every endpoint's OpenAPI schema below.
_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Insufficient funds."},
    404: {"model": ErrorResponse, "description": "Wallet not found."},
    409: {
        "model": ErrorResponse,
        "description": "Concurrency conflict — the wallet was modified by "
        "another request; retry.",
    },
    422: {"model": ErrorResponse, "description": "Invalid transaction amount."},
    423: {"model": ErrorResponse, "description": "The wallet is locked."},
}


def get_wallet_controller(request: Request) -> WalletController:
    """Resolves the app-wide `WalletController` singleton.

    Constructed once at startup in `main.py` (the composition root)
    and stored on `app.state`, so it is never re-instantiated per
    request — this is the dependency-injection seam between FastAPI's
    `Depends` and the rest of the Mizan Logic layers.
    """
    return request.app.state.wallet_controller


def _to_balance_response(wallet) -> WalletBalanceResponse:
    return WalletBalanceResponse(
        wallet_id=wallet.id,
        owner_id=wallet.owner_id,
        currency=wallet.currency,
        balance=wallet.balance,
        is_locked=wallet.is_locked,
        version=wallet.version,
    )


@router.get(
    "/{wallet_id}/balance",
    response_model=WalletBalanceResponse,
    responses={404: _ERROR_RESPONSES[404]},
    summary="Fetch a wallet's current balance",
    description=(
        "Returns a wallet's current balance, lock status, and "
        "optimistic-concurrency version. Read-only — never mutates "
        "the wallet or the transaction ledger."
    ),
)
async def get_wallet_balance(
    wallet_id: str,
    controller: WalletController = Depends(get_wallet_controller),
) -> WalletBalanceResponse:
    """Fetch a wallet's balance by id.

    - **wallet_id**: The wallet to look up.

    Returns **404** if no wallet exists with that id.
    """
    wallet = await controller.get_balance(wallet_id)
    return _to_balance_response(wallet)


@router.post(
    "/deposit",
    response_model=TransactionResponse,
    responses=_ERROR_RESPONSES,
    summary="Deposit funds into a wallet",
    description=(
        "Credits a wallet by the given amount. The amount is validated "
        "by the business-logic layer (must be a strictly positive, "
        "finite decimal) before any database transaction is opened, "
        "and the resulting balance update plus its ledger entry are "
        "committed together, atomically, via an optimistic-locking "
        "Unit of Work."
    ),
)
async def deposit(
    body: DepositRequest,
    controller: WalletController = Depends(get_wallet_controller),
) -> TransactionResponse:
    """Deposit funds into a wallet.

    - **wallet_id**: The wallet to credit.
    - **amount**: The amount to deposit; must be strictly positive.

    Returns **422** for an invalid amount, **404** if the wallet does
    not exist, **423** if it is locked, or **409** if a concurrent
    request modified the wallet first (safe to retry).
    """
    wallet = await controller.deposit(wallet_id=body.wallet_id, amount=body.amount)
    return TransactionResponse(
        transaction_type="deposit",
        wallet_id=wallet.id,
        amount=body.amount,
        new_balance=wallet.balance,
        version=wallet.version,
    )


@router.post(
    "/withdraw",
    response_model=TransactionResponse,
    responses=_ERROR_RESPONSES,
    summary="Withdraw funds from a wallet",
    description=(
        "Debits a wallet by the given amount. The withdrawal is "
        "rejected — without ever writing to the database — if it "
        "would overdraw the wallet's current balance, if the amount "
        "is invalid, or if the wallet is locked. On success, the "
        "balance update and its ledger entry are committed together, "
        "atomically."
    ),
)
async def withdraw(
    body: WithdrawRequest,
    controller: WalletController = Depends(get_wallet_controller),
) -> TransactionResponse:
    """Withdraw funds from a wallet.

    - **wallet_id**: The wallet to debit.
    - **amount**: The amount to withdraw; must be strictly positive
      and no greater than the wallet's current balance.

    Returns **422** for an invalid amount, **400** for insufficient
    funds, **404** if the wallet does not exist, **423** if it is
    locked, or **409** if a concurrent request modified the wallet
    first (safe to retry).
    """
    wallet = await controller.withdraw(wallet_id=body.wallet_id, amount=body.amount)
    return TransactionResponse(
        transaction_type="withdrawal",
        wallet_id=wallet.id,
        amount=body.amount,
        new_balance=wallet.balance,
        version=wallet.version,
    )


@router.post(
    "/transfer",
    response_model=TransferResponse,
    responses=_ERROR_RESPONSES,
    summary="Transfer funds between two wallets",
    description=(
        "Moves the given amount from the source wallet to the "
        "destination wallet. Both wallets' balances are validated and "
        "updated together, atomically, inside a single Unit of Work — "
        "either both balances change and both ledger entries are "
        "recorded, or neither is. The two wallets are locked in a "
        "fixed, deterministic order internally, so concurrent "
        "transfers between the same pair of wallets in opposite "
        "directions can never deadlock against each other."
    ),
)
async def transfer(
    body: TransferRequest,
    controller: WalletController = Depends(get_wallet_controller),
) -> TransferResponse:
    """Transfer funds between two wallets.

    - **source_wallet_id**: The wallet the funds leave.
    - **destination_wallet_id**: The wallet the funds arrive at.
    - **amount**: The amount to transfer; must be strictly positive
      and no greater than the source wallet's current balance.

    Returns **422** for an invalid amount, **400** for insufficient
    funds, **404** if either wallet does not exist, **423** if either
    is locked, or **409** if a concurrent request modified either
    wallet first (safe to retry).
    """
    source, destination = await controller.transfer(
        source_wallet_id=body.source_wallet_id,
        destination_wallet_id=body.destination_wallet_id,
        amount=body.amount,
    )
    return TransferResponse(
        source_wallet_id=source.id,
        destination_wallet_id=destination.id,
        amount=body.amount,
        new_source_balance=source.balance,
        new_destination_balance=destination.balance,
    )

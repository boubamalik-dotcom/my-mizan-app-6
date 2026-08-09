"""Layer 2 — Digital Wallet HTTP routes.

Routes are intentionally thin: they parse/validate transport-level
input, resolve the authenticated caller via `get_current_user`,
delegate to `WalletController`, and return its result as the
appropriate response schema. All business logic, ownership
enforcement, and domain-exception translation lives in
`WalletController` — this module must never contain any of it.

Every endpoint below requires a valid `Authorization: Bearer <token>`
header (enforced by the `get_current_user` dependency) — the Digital
Wallet has no unauthenticated endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from ...layer_4_data_access.repositories.user_repository import UserRecord
from ..auth.deps import get_current_user
from ..controllers.wallet_controller import WalletController
from ..schemas.wallet_schemas import (
    CreateWalletRequest,
    DepositRequest,
    ErrorResponse,
    TransactionResponse,
    TransferRequest,
    TransferResponse,
    WalletBalanceResponse,
    WithdrawRequest,
)

router = APIRouter(prefix="/wallet", tags=["wallet"])

#: Every error code `WalletController` (or the `get_current_user`
#: dependency) can raise, documented once and reused across every
#: endpoint's OpenAPI schema below.
_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Insufficient funds."},
    401: {"model": ErrorResponse, "description": "Missing or invalid access token."},
    403: {
        "model": ErrorResponse,
        "description": "The authenticated user does not own this wallet.",
    },
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
        user_id=wallet.user_id,
        currency=wallet.currency,
        balance=wallet.balance,
        is_locked=wallet.is_locked,
        version=wallet.version,
    )


@router.post(
    "",
    response_model=WalletBalanceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: _ERROR_RESPONSES[401],
        409: {
            "model": ErrorResponse,
            "description": "The caller already has a wallet in this currency.",
        },
    },
    summary="Create a new wallet for the authenticated user",
    description=(
        "Creates a new, zero-balance, unlocked wallet owned by the "
        "authenticated caller. `currency` defaults to `USD` if the "
        "request body is omitted. A user may hold at most one wallet "
        "per currency — creating a second wallet in a currency the "
        "caller already holds one in returns **409**."
    ),
)
async def create_wallet(
    body: CreateWalletRequest = CreateWalletRequest(),
    controller: WalletController = Depends(get_wallet_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> WalletBalanceResponse:
    """Create a new wallet for the authenticated caller.

    - **currency**: The three-letter currency code; defaults to `USD`.

    Requires a valid `Authorization: Bearer <token>` header. Returns
    **409** if the caller already has a wallet in the requested
    currency.
    """
    wallet = await controller.create_wallet(
        currency=body.currency, current_user_id=current_user.id
    )
    return _to_balance_response(wallet)


@router.get(
    "",
    response_model=WalletBalanceResponse,
    responses={
        401: _ERROR_RESPONSES[401],
        404: {
            "model": ErrorResponse,
            "description": "The caller has not provisioned a wallet yet.",
        },
    },
    summary="Fetch the authenticated user's own wallet",
    description=(
        "Returns the balance, currency, lock status, and optimistic-"
        "concurrency version of the wallet belonging to the "
        "authenticated caller — the lookup a client makes on start-up "
        "*before* deciding whether it needs to call `POST /wallet` to "
        "provision one. Returns **404** if the caller has not "
        "provisioned a wallet yet; it does not create one implicitly."
    ),
)
async def get_my_wallet(
    controller: WalletController = Depends(get_wallet_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> WalletBalanceResponse:
    """Fetch the authenticated caller's own wallet.

    Requires a valid `Authorization: Bearer <token>` header. Returns
    **404** if the caller has not provisioned a wallet yet — callers
    should treat that as "call `POST /wallet` next", not as an error
    to surface directly to the user.
    """
    wallet = await controller.get_my_wallet(current_user_id=current_user.id)
    return _to_balance_response(wallet)


@router.get(
    "/{wallet_id}/balance",
    response_model=WalletBalanceResponse,
    responses={
        401: _ERROR_RESPONSES[401],
        403: _ERROR_RESPONSES[403],
        404: _ERROR_RESPONSES[404],
    },
    summary="Fetch a wallet's current balance",
    description=(
        "Returns a wallet's current balance, lock status, and "
        "optimistic-concurrency version. Read-only — never mutates "
        "the wallet or the transaction ledger. Requires the caller to "
        "own the wallet."
    ),
)
async def get_wallet_balance(
    wallet_id: str,
    controller: WalletController = Depends(get_wallet_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> WalletBalanceResponse:
    """Fetch a wallet's balance by id.

    - **wallet_id**: The wallet to look up.

    Requires a valid `Authorization: Bearer <token>` header. Returns
    **404** if no wallet exists with that id, or **403** if it exists
    but does not belong to the authenticated caller.
    """
    wallet = await controller.get_balance(wallet_id, current_user_id=current_user.id)
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
        "Unit of Work. Requires the caller to own the wallet."
    ),
)
async def deposit(
    body: DepositRequest,
    controller: WalletController = Depends(get_wallet_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> TransactionResponse:
    """Deposit funds into a wallet.

    - **wallet_id**: The wallet to credit.
    - **amount**: The amount to deposit; must be strictly positive.

    Requires a valid `Authorization: Bearer <token>` header. Returns
    **422** for an invalid amount, **404** if the wallet does not
    exist, **403** if it does not belong to the authenticated caller,
    **423** if it is locked, or **409** if a concurrent request
    modified the wallet first (safe to retry).
    """
    wallet = await controller.deposit(
        wallet_id=body.wallet_id, amount=body.amount, current_user_id=current_user.id
    )
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
        "atomically. Requires the caller to own the wallet."
    ),
)
async def withdraw(
    body: WithdrawRequest,
    controller: WalletController = Depends(get_wallet_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> TransactionResponse:
    """Withdraw funds from a wallet.

    - **wallet_id**: The wallet to debit.
    - **amount**: The amount to withdraw; must be strictly positive
      and no greater than the wallet's current balance.

    Requires a valid `Authorization: Bearer <token>` header. Returns
    **422** for an invalid amount, **400** for insufficient funds,
    **404** if the wallet does not exist, **403** if it does not
    belong to the authenticated caller, **423** if it is locked, or
    **409** if a concurrent request modified the wallet first (safe to
    retry).
    """
    wallet = await controller.withdraw(
        wallet_id=body.wallet_id, amount=body.amount, current_user_id=current_user.id
    )
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
        "directions can never deadlock against each other. The caller "
        "must own the *source* wallet; the destination wallet may "
        "belong to any user — that is how a transfer differs from a "
        "deposit/withdrawal."
    ),
)
async def transfer(
    body: TransferRequest,
    controller: WalletController = Depends(get_wallet_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> TransferResponse:
    """Transfer funds between two wallets.

    - **source_wallet_id**: The wallet the funds leave. Must belong to
      the authenticated caller.
    - **destination_wallet_id**: The wallet the funds arrive at. May
      belong to any user.
    - **amount**: The amount to transfer; must be strictly positive
      and no greater than the source wallet's current balance.

    Requires a valid `Authorization: Bearer <token>` header. Returns
    **422** for an invalid amount, **400** for insufficient funds,
    **404** if either wallet does not exist, **403** if the caller
    does not own the source wallet, **423** if either wallet is
    locked, or **409** if a concurrent request modified either wallet
    first (safe to retry).
    """
    source, destination = await controller.transfer(
        source_wallet_id=body.source_wallet_id,
        destination_wallet_id=body.destination_wallet_id,
        amount=body.amount,
        current_user_id=current_user.id,
    )
    return TransferResponse(
        source_wallet_id=source.id,
        destination_wallet_id=destination.id,
        amount=body.amount,
        new_source_balance=source.balance,
        new_destination_balance=destination.balance,
    )

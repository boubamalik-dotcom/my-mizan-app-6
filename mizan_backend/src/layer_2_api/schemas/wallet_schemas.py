"""Layer 2 — Pydantic request/response contracts (DTOs) for the
Digital Wallet's REST API.

Amounts are modeled as `Decimal`, never `float`, all the way out to
the API boundary: Pydantic serializes `Decimal` as an exact JSON
number without any binary floating-point rounding, matching Layer 3's
own strict `decimal.Decimal`-only arithmetic
(`layer_3_business/wallet/wallet_service.py`).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DepositRequest(BaseModel):
    """Body for `POST /wallet/deposit`."""

    wallet_id: str = Field(..., min_length=1, description="The wallet to credit.")
    amount: Decimal = Field(
        ...,
        gt=0,
        description="The amount to deposit. Must be strictly positive.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"wallet_id": "b6e6b4b0-...", "amount": "50.00"}]
        }
    }


class WithdrawRequest(BaseModel):
    """Body for `POST /wallet/withdraw`."""

    wallet_id: str = Field(..., min_length=1, description="The wallet to debit.")
    amount: Decimal = Field(
        ...,
        gt=0,
        description="The amount to withdraw. Must be strictly positive and "
        "no greater than the wallet's current balance.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"wallet_id": "b6e6b4b0-...", "amount": "20.00"}]
        }
    }


class TransferRequest(BaseModel):
    """Body for `POST /wallet/transfer`."""

    source_wallet_id: str = Field(
        ..., min_length=1, description="The wallet the funds are transferred from."
    )
    destination_wallet_id: str = Field(
        ..., min_length=1, description="The wallet the funds are transferred to."
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        description="The amount to transfer. Must be strictly positive and "
        "no greater than the source wallet's current balance.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "source_wallet_id": "b6e6b4b0-...",
                    "destination_wallet_id": "9d8c9a1e-...",
                    "amount": "15.00",
                }
            ]
        }
    }


class WalletBalanceResponse(BaseModel):
    """Response body for `GET /wallet/{wallet_id}/balance`."""

    wallet_id: str
    owner_id: str
    currency: str
    balance: Decimal
    is_locked: bool
    version: int


class TransactionResponse(BaseModel):
    """Response body for `POST /wallet/deposit` and
    `POST /wallet/withdraw`: the resulting transaction status and the
    wallet's new balance."""

    status: Literal["success"] = "success"
    transaction_type: Literal["deposit", "withdrawal"]
    wallet_id: str
    amount: Decimal
    new_balance: Decimal
    version: int


class TransferResponse(BaseModel):
    """Response body for `POST /wallet/transfer`: the resulting
    transaction status and both wallets' new balances."""

    status: Literal["success"] = "success"
    transaction_type: Literal["transfer"] = "transfer"
    source_wallet_id: str
    destination_wallet_id: str
    amount: Decimal
    new_source_balance: Decimal
    new_destination_balance: Decimal


class ErrorResponse(BaseModel):
    """Standard error body for every REST endpoint's non-2xx
    responses."""

    detail: str

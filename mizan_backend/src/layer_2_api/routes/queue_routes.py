"""Layer 2 — Mizan Door clinic-queue HTTP routes.

Routes are intentionally thin: they resolve the caller, delegate to
`QueueController`, and marshal its records into response schemas. All
business logic, ownership enforcement, and domain-exception
translation lives in the controller — this module must never contain
any of it.

Mounted under `/api/v1` by `main.py`, so the paths below resolve to
`/api/v1/queues` and `/api/v1/queues/{clinic_id}/reservations`, which
is what `mizan_frontend`'s Mizan Door mini-program already calls.
"""
from __future__ import annotations

from typing import Optional

from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from ...layer_4_data_access.repositories.queue_repository import (
    ClinicQueueRecord,
    ReservationRecord,
)
from ...layer_4_data_access.repositories.user_repository import UserRecord
from ...layer_3_business.authz.roles import Permission
from ..auth.auth_controller import AuthController
from ..auth.deps import (
    get_current_user,
    get_current_user_or_none,
    require_permission,
)
from ..controllers.queue_controller import QueueController
from ..realtime.queue_broadcaster import QueueBroadcaster
from ..schemas.queue_schemas import (
    AdvanceQueueResponse,
    ClinicQueueResponse,
    ClinicResponse,
    ErrorResponse,
    QueueListResponse,
    ReservationResponse,
)

router = APIRouter(prefix="/queues", tags=["queues"])

#: Every error code `QueueController` can raise, documented once and
#: reused across the endpoints below.
_ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or invalid access token."},
    403: {
        "model": ErrorResponse,
        "description": "The reservation belongs to another patient.",
    },
    404: {"model": ErrorResponse, "description": "No such clinic or reservation."},
    409: {
        "model": ErrorResponse,
        "description": "The caller already holds a place in this clinic's queue.",
    },
    410: {
        "model": ErrorResponse,
        "description": "The reservation was already served or cancelled.",
    },
    422: {
        "model": ErrorResponse,
        "description": "The clinic is not accepting patients right now.",
    },
    503: {
        "model": ErrorResponse,
        "description": "Ticket numbering collided; retry the request.",
    },
}


def get_queue_controller(request: Request) -> QueueController:
    """Resolves the app-wide `QueueController` singleton.

    Constructed once at startup in `main.py` (the composition root) and
    stored on `app.state`, so it is never re-instantiated per request.
    """
    return request.app.state.queue_controller


def _to_queue_response(queue: ClinicQueueRecord) -> ClinicQueueResponse:
    return ClinicQueueResponse(
        clinic=ClinicResponse(
            id=queue.id,
            name=queue.name,
            specialty=queue.specialty,
            district=queue.district,
        ),
        waiting_count=queue.waiting_count,
        average_service_minutes=queue.service_rate_minutes,
        now_serving_ticket=queue.now_serving_ticket,
        is_accepting_patients=queue.is_accepting_patients,
        estimated_wait_minutes=queue.waiting_count * queue.service_rate_minutes,
    )


def _to_reservation_response(
    reservation: ReservationRecord,
) -> ReservationResponse:
    return ReservationResponse(
        id=reservation.id,
        clinic_id=reservation.clinic_id,
        clinic_name=reservation.clinic_name,
        # The derived "people ahead" figure, not the stored ticket —
        # see `queue_schemas.ReservationResponse.position`.
        position=reservation.people_ahead,
        ticket_number=reservation.ticket_number,
        estimated_wait_minutes=reservation.estimated_wait_minutes,
        status=reservation.status.value,
        joined_at=reservation.created_at,
    )


@router.get(
    "",
    response_model=QueueListResponse,
    summary="List every clinic's queue",
    description=(
        "Returns each clinic with the number of people currently "
        "waiting and the wait a patient joining now could expect.\n\n"
        "Authentication is **optional**: anyone may see how long the "
        "queues are, since a patient deciding whether it is worth "
        "leaving the house should not have to sign in first. Presenting "
        "a valid bearer token additionally returns `reservation` — the "
        "caller's own active place, if they hold one. An expired or "
        "malformed token is treated as no token rather than rejected, "
        "so a stale credential still yields the public view."
    ),
)
async def list_queues(
    controller: QueueController = Depends(get_queue_controller),
    current_user: Optional[UserRecord] = Depends(get_current_user_or_none),
) -> QueueListResponse:
    """List every clinic's queue, plus the caller's own place if they
    presented a token and hold one."""
    queues, reservation = await controller.list_queues(
        current_user_id=current_user.id if current_user is not None else None
    )
    return QueueListResponse(
        queues=[_to_queue_response(queue) for queue in queues],
        reservation=(
            _to_reservation_response(reservation) if reservation is not None else None
        ),
    )


@router.post(
    "/{clinic_id}/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: _ERROR_RESPONSES[401],
        404: _ERROR_RESPONSES[404],
        409: _ERROR_RESPONSES[409],
        422: _ERROR_RESPONSES[422],
        503: _ERROR_RESPONSES[503],
    },
    summary="Take a place in a clinic's queue",
    description=(
        "Issues the next ticket for `clinic_id` to the authenticated "
        "caller and returns their place in the queue.\n\n"
        "Ticket numbers are assigned under a row lock on the clinic, so "
        "two patients joining simultaneously receive consecutive "
        "numbers and never the same one.\n\n"
        "Returns **409** if the caller already holds a place in this "
        "clinic, **422** if the clinic has stopped admitting patients, "
        "and **404** if no such clinic exists."
    ),
)
async def join_queue(
    clinic_id: str,
    controller: QueueController = Depends(get_queue_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> ReservationResponse:
    """Take the next place in a clinic's queue.

    Requires a valid `Authorization: Bearer <token>` header — a
    reservation belongs to a person, so the server has to know who is
    asking.
    """
    reservation = await controller.join_queue(
        clinic_id=clinic_id, current_user_id=current_user.id
    )
    return _to_reservation_response(reservation)


@router.post(
    "/{clinic_id}/next",
    response_model=AdvanceQueueResponse,
    responses={
        401: _ERROR_RESPONSES[401],
        403: {
            "model": ErrorResponse,
            "description": "The caller may not advance clinic queues.",
        },
        404: _ERROR_RESPONSES[404],
    },
    summary="Call the next patient",
    description=(
        "Completes the consultation in progress and admits the patient "
        "holding the lowest outstanding ticket.\n\n"
        "**Staff only.** Requires the `queue:advance` permission, held "
        "by the `clinic_staff` and `admin` roles and by no ordinary "
        "patient — someone standing in the queue who could advance it "
        "could serve themselves to the front of it.\n\n"
        "The transition happens under a row lock on the clinic, so two "
        "receptionists pressing the button at the same moment advance "
        "the queue by two patients rather than one silently swallowing "
        "the other.\n\n"
        "Pressing this on an empty queue is **not** an error: the "
        "response reports `queue_empty` and nothing changes."
    ),
)
async def advance_queue(
    clinic_id: str,
    controller: QueueController = Depends(get_queue_controller),
    _: UserRecord = Depends(require_permission(Permission.QUEUE_ADVANCE)),
) -> AdvanceQueueResponse:
    """Call the next patient in a clinic's queue.

    Requires a valid `Authorization: Bearer <token>` for an account
    holding `queue:advance`.
    """
    advance = await controller.advance_queue(clinic_id=clinic_id)
    return AdvanceQueueResponse(
        outcome=advance.outcome.value,
        now_serving=(
            _to_reservation_response(advance.now_serving)
            if advance.now_serving is not None
            else None
        ),
        completed=(
            _to_reservation_response(advance.completed)
            if advance.completed is not None
            else None
        ),
        queue=_to_queue_response(advance.queue),
    )


def get_queue_broadcaster_ws(websocket: WebSocket) -> QueueBroadcaster:
    """Resolves the app-wide `QueueBroadcaster` for a WebSocket route.

    A separate resolver from the HTTP one because a WebSocket handler
    receives a `WebSocket`, not a `Request`; both reach the same
    singleton on `app.state`.
    """
    return websocket.app.state.queue_broadcaster


def get_auth_controller_ws(websocket: WebSocket) -> AuthController:
    """The auth controller, for the same reason."""
    return websocket.app.state.auth_controller


@router.websocket("/ws/{clinic_id}")
async def queue_websocket(
    websocket: WebSocket,
    clinic_id: str,
    token: str | None = Query(
        default=None,
        description=(
            "JWT access token issued by POST /auth/login, e.g. "
            "ws://.../api/v1/queues/ws/{clinic_id}?token=.... Required — "
            "standard WebSocket APIs cannot send an Authorization header."
        ),
    ),
    broadcaster: QueueBroadcaster = Depends(get_queue_broadcaster_ws),
    auth_controller: AuthController = Depends(get_auth_controller_ws),
) -> None:
    """Live updates for one clinic's queue.

    The server pushes a frame whenever the clinic's queue changes —
    someone joins, someone cancels, or reception calls the next
    patient::

        {
          "event": "queue_updated",
          "clinic_id": "...",
          "waiting_count": 3,
          "now_serving_ticket": 7,
          "is_accepting_patients": true,
          "average_service_minutes": 8,
          "estimated_wait_minutes": 24
        }

    **The frame carries no patient information at all** — no names, no
    ids, nothing about who is in the queue. A client that needs its own
    position asks `GET /api/v1/queues` with its token; the socket only
    ever says that this clinic's queue moved. That is a deliberate
    constraint, not an omission: a live stream of who is sitting in
    which clinic, at a clinic whose specialty implies why, is a medical
    privacy breach however convenient the payload would be.

    Authentication is required even though the same figures are
    readable anonymously over REST. Reading is a request that ends; a
    socket is a resource held open, and this bounds who can hold one.

    Nothing is expected from the client. Frames it sends are ignored;
    the receive loop exists only to notice the connection closing.
    """
    if not token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required."
        )
        return

    user = await auth_controller.resolve_user_or_none(token)
    if user is None:
        # Closed before accepting, so a rejected client cannot tell our
        # refusal apart from a server that never saw the request.
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token."
        )
        return

    # One registration per socket, not per user: the same patient may
    # legitimately have the queue open on a phone and a laptop, and a
    # second tab must not silently evict the first.
    client_id = f"{user.id}:{uuid4().hex}"
    await broadcaster.connect(
        clinic_id=clinic_id, client_id=client_id, websocket=websocket
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(clinic_id=clinic_id, client_id=client_id)


@router.delete(
    "/reservations/{reservation_id}",
    response_model=ReservationResponse,
    responses={
        401: _ERROR_RESPONSES[401],
        403: _ERROR_RESPONSES[403],
        404: _ERROR_RESPONSES[404],
        410: _ERROR_RESPONSES[410],
    },
    summary="Give up a place in a queue",
    description=(
        "Cancels the caller's own reservation. The row is kept with a "
        "`cancelled` status rather than deleted, so the ticket number "
        "is never reissued and the clinic's record of the day stays "
        "complete.\n\n"
        "Returns **403** if the reservation belongs to another patient "
        "and **410** if it was already served or cancelled."
    ),
)
async def cancel_reservation(
    reservation_id: str,
    controller: QueueController = Depends(get_queue_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> ReservationResponse:
    """Give up the caller's own place in a queue."""
    reservation = await controller.cancel_reservation(
        reservation_id=reservation_id, current_user_id=current_user.id
    )
    return _to_reservation_response(reservation)

import logging

import stripe
from fastapi import APIRouter, HTTPException, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.billing.models import WebhookStatusResponse
from app.billing.service import sync_stripe_to_postgres
from app.config import settings
from app.postgres import get_db_session

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# Events we track (all subscription-related)
TRACKED_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "invoice_payment.paid",  # Newer Stripe event fired alongside invoice.paid
]


@router.post("/stripe", response_model=WebhookStatusResponse)
async def stripe_webhook(request: Request):
    """Stripe webhook: treat Stripe as source of truth and sync Postgres from Stripe."""

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(400, "Missing stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    async for db in get_db_session():
        await process_webhook_event(event, db)

    return {"status": "success"}


async def process_webhook_event(event: dict, db: AsyncSession):
    """Extract customer_id per event type and sync."""

    event_type = event["type"]

    if event_type not in TRACKED_EVENTS:
        logger.info(f"Ignoring event: {event_type}")
        return

    event_object = event["data"]["object"]
    customer_id = None

    # Extract customer_id based on event type
    if event_type == "checkout.session.completed":
        # Checkout Session object
        customer_id = event_object.get("customer")

    elif event_type.startswith("customer.subscription."):
        # Subscription object
        customer_id = event_object.get("customer")

    elif event_type.startswith("invoice.") or event_type.startswith("invoice_payment."):
        # Invoice / InvoicePayment object
        customer_id = event_object.get("customer")

    if not customer_id:
        logger.warning(f"No customer in {event_type}")
        return

    logger.info(f"Processing {event_type} for customer {customer_id}")

    await sync_stripe_to_postgres(customer_id, db)

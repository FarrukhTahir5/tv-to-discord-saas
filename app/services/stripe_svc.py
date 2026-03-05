import stripe
from app.config import settings

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key


async def create_stripe_customer(email: str, user_id: str) -> str:
    """Create a Stripe customer and return the customer ID."""
    customer = stripe.Customer.create(
        email=email,
        metadata={"user_id": user_id},
    )
    return customer.id


async def create_checkout_session(
    customer_id: str, price_id: str, success_url: str, cancel_url: str
) -> str:
    """Create a Stripe checkout session and return the session URL."""
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url

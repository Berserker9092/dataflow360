from pydantic import BaseModel
from typing import Literal

class OrderItem(BaseModel):
    product_id: str
    quantity: int
    item_total: int   # XOF, pas de décimales

class CheckoutEvent(BaseModel):
    event_id: str
    event_type: str
    order_id: str
    customer_id: str
    order_total_amount: int        # XOF, pas de décimales
    currency: str
    client_ip: str
    ip_country: str
    payment_method: str
    payment_source_country: str | None = None   # vide si paiement cash
    payment_status: Literal["approved", "pending", "failed"]
    payment_attempt: int
    event_timestamp: str
    items: list[OrderItem] | None = None   # absent dans le CSV brut, ajouté par le producteur
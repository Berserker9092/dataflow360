from pydantic import BaseModel
from typing import Literal
 
class PaymentInfo(BaseModel):
    method: str
    source_country: str | None = None   # null si paiement cash
    attempt_number: int
    status: Literal["success", "failed"]
 
class OrderItem(BaseModel):
    product_id: str
    quantity: int
    unit_price_xof: int   # XOF n'a pas de décimales
 
class CheckoutEvent(BaseModel):
    order_id: str
    customer_id: str
    items: list[OrderItem]
    delivery_address: str
    payment: PaymentInfo
    client_ip: str
    ip_country: str
    event_timestamp: str
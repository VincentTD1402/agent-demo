"""Đăng ký mọi model vào Base.metadata (Alembic và test import module này)."""
from app.db.models.catalog import Product, ProductEmbedding
from app.db.models.conversation import Conversation, ToolAuditLog
from app.db.models.knowledge import KbChunk, KbDocument
from app.db.models.order import Order, OrderItem
from app.db.models.refund import Refund
from app.db.models.support import Notification, StatusEvent, SupportTicket
from app.db.models.user import RefreshToken, User

__all__ = [
    "Conversation", "KbChunk", "KbDocument", "Notification", "Order", "OrderItem", "Product",
    "ProductEmbedding", "RefreshToken", "Refund", "StatusEvent", "SupportTicket", "ToolAuditLog", "User",
]

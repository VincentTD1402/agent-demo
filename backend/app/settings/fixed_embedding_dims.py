"""Số chiều embedding cố định: cột vector của KB/sản phẩm (revision 0003, 0007) và model khai báo `Vector(1024)`.

Đổi số chiều phải kèm một revision `ALTER COLUMN ... TYPE vector(M)`; cho tới lúc đó mọi tiến trình từ chối giá trị khác.
"""

FIXED_EMBEDDING_DIMS = 1024


def require_fixed_embedding_dims(value: int) -> int:
    if value != FIXED_EMBEDDING_DIMS:
        raise ValueError(
            f"EMBEDDING_DIMS phải là {FIXED_EMBEDDING_DIMS} (cột vector của schema cố định); nhận {value}. "
            "Đổi số chiều cần revision Alembic riêng."
        )
    return value

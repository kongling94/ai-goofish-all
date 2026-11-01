from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ProductInput(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    price: float = Field(gt=0)
    images: list[str] = Field(min_length=1, max_length=9)
    category: str = ''
    source_item_id: str | None = None
    delivery_type: Literal['fixed', 'stock'] = 'stock'
    fixed_content: str = ''

    @field_validator('sku', 'title', 'description')
    @classmethod
    def strip_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('不能为空')
        return value

    @field_validator('images')
    @classmethod
    def validate_images(cls, values):
        if any(not value.startswith(('https://', 'http://', 'data:image/')) for value in values):
            raise ValueError('图片需要 HTTP(S) URL 或图片 data URL')
        return values


class PublishInput(BaseModel):
    account_id: str = Field(min_length=1)


class StockInput(BaseModel):
    codes: list[str] = Field(min_length=1)

    @field_validator('codes')
    @classmethod
    def validate_codes(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('卡密不能为空')
        return list(dict.fromkeys(value.strip() for value in values))


class PreviewOrderInput(BaseModel):
    product_id: int
    order_id: str = Field(min_length=1)
    payment_status: Literal['paid', 'cancelled', 'refunding', 'pending_payment'] = 'paid'
    send_result: Literal['success', 'unknown'] = 'success'


class ReconcileInput(BaseModel):
    seller_item_id: str = Field(min_length=1)
    publish_log_id: int | None = None

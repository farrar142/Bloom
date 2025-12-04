"""Products Repository"""

from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime

from bloom.core import Repository, PostConstruct

from .entity import Product

logger = logging.getLogger(__name__)


@Repository
class ProductRepository:
    """상품 저장소"""

    def __init__(self):
        self._data: dict[int, Product] = {}
        self._next_id = 1

    @PostConstruct
    async def initialize(self):
        # 샘플 상품 생성
        products = [
            ("MacBook Pro", "Apple M3 Max 노트북", 3500000, 10),
            ("iPhone 15 Pro", "Apple 스마트폰", 1550000, 50),
            ("AirPods Pro", "무선 이어폰", 359000, 100),
        ]
        for name, desc, price, stock in products:
            product = Product()
            product.id = self._next_id
            product.name = name
            product.description = desc
            product.price = price
            product.stock = stock
            product.is_available = True
            product.created_at = datetime.now()
            self._data[product.id] = product
            self._next_id += 1
        logger.info(f"ProductRepository initialized with {len(products)} products")

    async def save(self, product: Product) -> Product:
        if not product.id:
            product.id = self._next_id
            self._next_id += 1
            product.created_at = datetime.now()
        self._data[product.id] = product
        return product

    async def find_by_id(self, product_id: int) -> Optional[Product]:
        return self._data.get(product_id)

    async def find_all(self) -> list[Product]:
        return list(self._data.values())

    async def update_stock(self, product_id: int, quantity: int) -> bool:
        product = self._data.get(product_id)
        if product and product.stock >= quantity:
            product.stock -= quantity
            return True
        return False

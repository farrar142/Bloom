"""Products Service"""

from __future__ import annotations

import logging
from typing import Optional

from bloom.core import Service, PostConstruct

from .entity import Product
from .repository import ProductRepository

logger = logging.getLogger(__name__)


@Service
class ProductService:
    """상품 서비스"""

    product_repo: ProductRepository

    @PostConstruct
    async def initialize(self):
        logger.info("ProductService initialized")

    async def get_product(self, product_id: int) -> Optional[Product]:
        """상품 조회"""
        return await self.product_repo.find_by_id(product_id)

    async def get_all_products(self) -> list[Product]:
        """모든 상품 조회"""
        return await self.product_repo.find_all()

    async def check_stock(self, product_id: int, quantity: int) -> bool:
        """재고 확인"""
        product = await self.product_repo.find_by_id(product_id)
        if product:
            return product.stock >= quantity
        return False

    async def reserve_stock(self, product_id: int, quantity: int) -> bool:
        """재고 차감"""
        return await self.product_repo.update_stock(product_id, quantity)

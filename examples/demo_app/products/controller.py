"""Products Controller"""

from __future__ import annotations

from bloom.web import (
    Controller,
    GetMapping,
    RequestMapping,
    JSONResponse,
    PathVariable,
)

from .service import ProductService


@Controller
@RequestMapping("/api/products")
class ProductController:
    """상품 API"""

    product_service: ProductService

    @GetMapping
    async def list_products(self) -> JSONResponse:
        """상품 목록"""
        products = await self.product_service.get_all_products()
        return JSONResponse(
            {
                "products": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "price": p.price,
                        "stock": p.stock,
                        "is_available": p.is_available,
                    }
                    for p in products
                ]
            }
        )

    @GetMapping("/{product_id}")
    async def get_product(self, product_id: PathVariable[int]) -> JSONResponse:
        """상품 상세"""
        product = await self.product_service.get_product(product_id)
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        return JSONResponse(
            {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": product.price,
                "stock": product.stock,
                "is_available": product.is_available,
            }
        )

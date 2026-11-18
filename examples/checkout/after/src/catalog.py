PRICES = {"tea": 3.5, "coffee": 4.25}


def price_for(product_id: str) -> float:
    try:
        return PRICES[product_id]
    except KeyError:
        raise KeyError(f"unknown product: {product_id}") from None

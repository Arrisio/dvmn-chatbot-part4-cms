import asyncio
import logging
import httpx
from settings import MoltenSettings
from datetime import datetime

# наличие всех параметров MoltenSettings обязательно для работы этого модуля. Поэтому считаю оправданным объявлени settings в этом месте
settings = MoltenSettings()

logger = logging.getLogger(__name__)

MOLTEN_AUTH_DATA: dict = {}
MOLTEN_SESSION: httpx.AsyncClient = httpx.AsyncClient(http2=True)


async def refresh_auth_data():
    logger.debug("trying to refresh molten auth data")
    global MOLTEN_AUTH_DATA
    response = await MOLTEN_SESSION.post(
        url=f"{settings.MOLTEN_URL}/oauth/access_token",
        data={"client_id": settings.MOLTEN_CLIENT_ID, "grant_type": "implicit"},
    )
    response.raise_for_status()
    MOLTEN_AUTH_DATA = response.json()
    logger.info(f"molten auth data successfully refreshed {MOLTEN_AUTH_DATA}")


class MoltenAuth(httpx.Auth):
    async def async_auth_flow(self, request, token_expires_preservation_sec=10):
        global MOLTEN_AUTH_DATA

        if (
            not MOLTEN_AUTH_DATA
            or datetime.utcfromtimestamp(MOLTEN_AUTH_DATA["expires"] - token_expires_preservation_sec)
            < datetime.utcnow()
        ):
            await refresh_auth_data()

        request.headers["Authorization"] = f"Bearer {MOLTEN_AUTH_DATA['access_token']}"
        response = yield request

        if response.status_code == 401:
            logger.error("auth receive 401 code. trying again...")
            await refresh_auth_data()

            request.headers["Authorization"] = f"Bearer {MOLTEN_AUTH_DATA['access_token']}"
            yield request


async def get_product_list() -> list[dict]:
    response = await MOLTEN_SESSION.get(
        f"{settings.MOLTEN_URL}/v2/products",
        auth=MoltenAuth(),
    )
    logger.debug("product list received")
    return response.json()["data"]


async def get_product_details(product_id: str) -> dict:
    response = await MOLTEN_SESSION.get(
        f"{settings.MOLTEN_URL}/v2/products/{product_id}",
        auth=MoltenAuth(),
    )
    logger.debug("product detail received")
    return response.json()["data"]


async def get_product_main_image_link(product: dict) -> str:
    main_image_id = product["relationships"]["main_image"]["data"]["id"]

    response = await MOLTEN_SESSION.get(
        url=f"https://api.moltin.com/v2/files/{main_image_id}",
        auth=MoltenAuth(),
    )

    logger.debug("product image link received")
    return response.json()["data"]["link"]["href"]


class AddToCartException(Exception):
    pass


async def add_to_cart(user_id: str, product_id: str):
    try:
        response = await MOLTEN_SESSION.post(
            f"{settings.MOLTEN_URL}/v2/carts/{user_id}/items",
            auth=MoltenAuth(),
            json={"data": {"id": product_id, "type": "cart_item", "quantity": 1}},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        logger.error(err)
        raise AddToCartException


async def get_cart_items(user_id: str):
    response = await MOLTEN_SESSION.get(
        f"{settings.MOLTEN_URL}/v2/carts/{user_id}/items",
        auth=MoltenAuth(),
    )
    response.raise_for_status()
    return response.json()["data"]


async def get_cart_price(user_id: str) -> str:
    response = await MOLTEN_SESSION.get(
        f"{settings.MOLTEN_URL}/v2/carts/{user_id}",
        auth=MoltenAuth(),
    )
    response.raise_for_status()
    return response.json()["data"]["meta"]["display_price"]["with_tax"]["formatted"]


async def remove_item_from_cart(user_id: str, item_id: str):
    response = await MOLTEN_SESSION.delete(
        f"{settings.MOLTEN_URL}/v2/carts/{user_id}/items/{item_id}",
        auth=MoltenAuth(),
    )
    response.raise_for_status()


class CreateCustomerException(Exception):
    pass


async def create_customer(customer_id: str, customer_name: str, customer_email: str):
    try:
        response = await MOLTEN_SESSION.post(
            url=f"{settings.MOLTEN_URL}/v2/customers/{customer_id}",
            auth=MoltenAuth(),
            json={
                "data": {
                    "type": "customer",
                    "name": customer_name,
                    "email": customer_email,
                }
            },
        )
        if not response.status_code != 409:  # 409 возвращается, если клиент уже существует, что не является ошибкой
            response.raise_for_status()
    except httpx.HTTPStatusError as err:
        logger.error(err)
        raise CreateCustomerException

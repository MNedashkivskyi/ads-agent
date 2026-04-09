from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CustomerInfo:
    descriptive_name: str
    currency: str
    timezone: str
    is_manager: bool


class GoogleAdsClientPort(Protocol):
    async def list_accessible_customers(self, refresh_token: str) -> list[str]: ...

    async def get_customer_info(self, refresh_token: str, customer_id: str) -> CustomerInfo: ...

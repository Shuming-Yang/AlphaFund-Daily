"""TDCC 基金資訊觀測站 HTTP 客戶端。

存取要點（見 m1-design.md / ADR-0005）：
- 需先 GET 首頁暖機取得 session cookie。
- POST 需帶對應頁面的 Referer，否則回傳 403（非 reCAPTCHA 擋）。
- 純 HTTP 即可，無需無頭瀏覽器。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_fixed

from .config import (
    DEFAULT_HEADERS,
    FUND_PAGE_SIZE,
    TDCC_BASE_URL,
    TDCC_DIVIDEND_QUERY,
    TDCC_DIVIDEND_QUERY_TYPE,
    TDCC_FUND_DETAILS,
    TDCC_FUND_QUERY,
    TDCC_ORG_BASIC,
    TDCC_ORG_DETAIL,
    REFERER_DIVIDEND,
    REFERER_FUND_DETAILS,
    REFERER_FUND_SEARCH,
    REFERER_ORG_SEARCH,
    REFERER_SALES_FUND,
)

logger = logging.getLogger(__name__)

_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


def _is_retryable_exc(exc: BaseException) -> bool:
    """可重試例外：404（查無配息資料）屬正常結果，不重試。"""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code != 404
    return isinstance(exc, _RETRYABLE)


class TdccClient:
    """管理 cookie session 與 TDCC API 呼叫。"""

    def __init__(
        self,
        base_url: str = TDCC_BASE_URL,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers=dict(DEFAULT_HEADERS),
            follow_redirects=True,
            transport=transport,
        )
        self._warmed = False

    def warmup(self) -> None:
        """GET 首頁以取得 session cookie。"""
        self._client.get("/")
        self._warmed = True

    def _post(self, path: str, payload: dict[str, Any], referer: str) -> dict[str, Any]:
        if not self._warmed:
            self.warmup()
        resp = self._client.post(path, json=payload, headers={"Referer": referer})
        resp.raise_for_status()
        return resp.json()

    @retry(
        retry=retry_if_exception_type(_RETRYABLE + (httpx.HTTPStatusError,)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def query_org_basic(self, org_type: str) -> list[dict[str, str]]:
        """依機構類型查詢機構清單（A=投信, B=投顧, K=證券商, N=銀行…）。"""
        data = self._post(TDCC_ORG_BASIC, {"orgType": org_type}, REFERER_ORG_SEARCH)
        return list(data.get("list", []))

    @retry(
        retry=retry_if_exception_type(_RETRYABLE + (httpx.HTTPStatusError,)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def query_org_detail(self, org_code: str) -> list[dict[str, str]]:
        """依機構代碼查詢其上架基金（機構查詢 > 銷售基金）。"""
        data = self._post(TDCC_ORG_DETAIL, {"orgCode": org_code}, REFERER_SALES_FUND)
        return list(data.get("list", []))

    @retry(
        retry=retry_if_exception_type(_RETRYABLE + (httpx.HTTPStatusError,)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def _query_funds_page(self, page: int, page_size: int, currency: str) -> dict[str, Any]:
        payload = {
            "queryFundName": "",
            "organizeCode": "all",
            "fundAsset": "all",
            "fundAssetD": "all",
            "fundInv": "all",
            "fundInvD": "all",
            "agent": "all",
            "fundAllot": ["all"],
            "fundShare": ["all"],
            "establishYear": ["all"],
            "currency": [currency],
            "_pageNum": page,
            "_pageSize": page_size,
        }
        return self._post(TDCC_FUND_QUERY, payload, REFERER_FUND_SEARCH)

    def query_all_funds(self, currency: str = "all") -> list[dict[str, Any]]:
        """分頁抓取全部境外基金記錄（含幣別、最新淨值、報酬率）。"""
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._query_funds_page(page, FUND_PAGE_SIZE, currency)
            items = data.get("list") or []
            records.extend(items)
            total = int(data.get("total") or 0)
            if not data.get("hasNextPage") or len(records) >= total:
                break
            page += 1
            if page > 200:
                logger.warning("超過 200 頁上限，停止分頁")
                break
        return records

    @retry(
        retry=retry_if_exception(_is_retryable_exc),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def _query_dividend_page(
        self, fund_code: str, begin: str, end: str, page: int, page_size: int
    ) -> dict[str, Any]:
        """查單一基金某頁配息紀錄。begin/end 格式 YYYY/MM（配息基準日區間）。"""
        payload = {
            "_pageNum": page,
            "_pageSize": page_size,
            "queryType": TDCC_DIVIDEND_QUERY_TYPE,
            "searchName": fund_code,
            "organizeCode": "",
            "fundCode": "",
            "fundClassCode": "",
            "asiFreqList": [],
            "baseBeginDate": begin,
            "baseEndDate": end,
        }
        return self._post(TDCC_DIVIDEND_QUERY, payload, REFERER_DIVIDEND)

    def query_dividend(self, fund_code: str, begin: str, end: str) -> list[dict[str, Any]]:
        """依基金代碼查詢配息紀錄（分頁）。

        begin/end 為配息基準日區間（YYYY/MM）；無資料（404）回傳空串列。
        注意：TDCC searchName 為子字串比對，可能命中其他代碼含相同子串之基金
        （如 0385 亦命中 LU2861038557），故回傳僅保留 fundCode 完全相符之紀錄。
        """
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                data = self._query_dividend_page(fund_code, begin, end, page, FUND_PAGE_SIZE)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return []
                raise
            items = data.get("list") or []
            records.extend(items)
            total = int(data.get("total") or 0)
            if not data.get("hasNextPage") or len(records) >= total:
                break
            page += 1
            if page > 50:
                logger.warning("配息分頁超過 50 頁上限，停止分頁（%s）", fund_code)
                break
        return [r for r in records if str(r.get("fundCode")) == fund_code]

    @retry(
        retry=retry_if_exception(_is_retryable_exc),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def _query_fund_details(self, fund_code: str) -> dict[str, Any]:
        return self._post(TDCC_FUND_DETAILS, {"fundCode": fund_code}, REFERER_FUND_DETAILS)

    def query_fund_details(self, fund_code: str) -> dict[str, Any]:
        """查單一基金基本資料（風險報酬等級 / 資產類別 / 投資類型）。

        無資料或格式異常時回傳空 dict（不中斷管道）。
        """
        try:
            data = self._query_fund_details(fund_code)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 400):
                return {}
            raise
        ft = data.get("fundType") or {}
        return {
            "risk_level": str(ft.get("fundRiskLevelTxt") or ""),
            "asset_class": str(ft.get("fundAssetName") or ""),
            "invest_type": str(ft.get("fundInvTypeName") or ""),
        }

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TdccClient":
        self.warmup()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

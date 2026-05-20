"""
政府採購網連線檢測
"""

import logging
import requests

from config import config

logger = logging.getLogger(__name__)

PCC_TEST_URL = f"{config.PCC_BASE_URL}/prkms/tpAppeal/common/indexTpAppeal"


def check_pcc_network(timeout: int = 20) -> dict:
    """
    檢測本機是否能連上政府電子採購網。

    Returns:
        dict: ok, message, status_code, detail
    """
    proxies = {}
    if config.HTTPS_PROXY:
        proxies["https"] = config.HTTPS_PROXY
    if config.HTTP_PROXY:
        proxies["http"] = config.HTTP_PROXY

    try:
        resp = requests.get(
            PCC_TEST_URL,
            timeout=timeout,
            allow_redirects=True,
            proxies=proxies or None,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )
        if resp.status_code < 400:
            return {
                "ok": True,
                "message": f"可連線政府採購網（HTTP {resp.status_code}）",
                "status_code": resp.status_code,
                "detail": "",
            }
        return {
            "ok": False,
            "message": f"政府採購網回應異常（HTTP {resp.status_code}）",
            "status_code": resp.status_code,
            "detail": resp.text[:200],
        }

    except requests.exceptions.ConnectTimeout:
        return {
            "ok": False,
            "message": "連線逾時：無法在時限內連上 web.pcc.gov.tw",
            "status_code": None,
            "detail": "常見原因：公司防火牆、需 VPN、或網路不穩",
        }
    except requests.exceptions.SSLError as e:
        return {
            "ok": False,
            "message": "SSL 握手失敗（與 Chrome 的 net_error -101 類似）",
            "status_code": None,
            "detail": str(e)[:300],
        }
    except requests.exceptions.ConnectionError as e:
        err = str(e)
        if "10061" in err or "refused" in err.lower():
            detail = "連線被拒絕"
        elif "10060" in err or "timed out" in err.lower():
            detail = "連線逾時"
        else:
            detail = err[:300]
        return {
            "ok": False,
            "message": "無法建立連線至政府採購網",
            "status_code": None,
            "detail": detail,
        }
    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"網路請求失敗：{type(e).__name__}",
            "status_code": None,
            "detail": str(e)[:300],
        }

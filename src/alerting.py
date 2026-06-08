from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from threading import Lock
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .config import ALERT_NOTIFICATION_CONFIG


LOGGER = logging.getLogger(__name__)

BASE_ALERT_CONFIG: Dict[str, Any] = {
    "trigger_threshold": 2.0,
    "cooldown_minutes": 10,
    "popup_enabled": True,
    "email": {
        "enabled": False,
        "smtp_host": "",
        "smtp_port": 465,
        "username": "",
        "password": "",
        "sender": "",
        "recipients": "",
        "security": "ssl",
        "subject_prefix": "[升贴水提醒]",
    },
    "feishu": {
        "enabled": False,
        "webhook_url": "",
        "secret": "",
    },
    "wecom": {
        "enabled": False,
        "webhook_url": "",
    },
}

def _now() -> datetime:
    return datetime.now()


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


DEFAULT_ALERT_CONFIG: Dict[str, Any] = _deep_merge(BASE_ALERT_CONFIG, ALERT_NOTIFICATION_CONFIG)


def _to_float(value: Any, default: float) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _format_log_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "-")


def _delivery_summary(deliveries: List[Dict[str, Any]]) -> str:
    if not deliveries:
        return "none"
    return ", ".join(
        f"{item.get('channel', '?')}:{item.get('status', '?')}"
        for item in deliveries
    )


class AlertNotificationManager:
    def __init__(self, config_override: Optional[Dict[str, Any]] = None) -> None:
        self._lock = Lock()
        self._config = self._sanitize_config(_deep_merge(DEFAULT_ALERT_CONFIG, config_override or {}))
        self._runtime_state: Dict[str, Dict[str, Any]] = {}
        LOGGER.info("alert manager initialized %s", self._config_summary(self._config))

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._config)

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            merged = _deep_merge(self._config, updates or {})
            self._config = self._sanitize_config(merged)
            updated = copy.deepcopy(self._config)
        LOGGER.info("alert config updated %s", self._config_summary(updated))
        return updated

    def handle_snapshot(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        config = self.get_config()
        threshold = abs(_to_float(config.get("trigger_threshold"), DEFAULT_ALERT_CONFIG["trigger_threshold"]))
        cooldown_minutes = max(_to_int(config.get("cooldown_minutes"), DEFAULT_ALERT_CONFIG["cooldown_minutes"]), 0)
        cooldown = timedelta(minutes=cooldown_minutes)
        now = _now()
        pending_events: List[Dict[str, Any]] = []
        decision_logs: List[Dict[str, Any]] = []

        LOGGER.info(
            "alert evaluation start generated_at=%s symbols=%s threshold=%.4f cooldown_minutes=%s",
            snapshot.get("generated_at"),
            ",".join(sorted(snapshot.get("symbols", {}).keys())),
            threshold,
            cooldown_minutes,
        )

        with self._lock:
            for symbol, symbol_data in snapshot.get("symbols", {}).items():
                main_contract = symbol_data.get("main_contract") or {}
                premium_rate = _to_float(main_contract.get("premium_rate"), 0.0)
                quote_time = str(main_contract.get("quote_time") or "")
                contract_code = str(main_contract.get("contract_code") or "").strip()
                state = self._runtime_state.get(symbol, {})
                is_triggered = bool(contract_code) and abs(premium_rate) >= threshold
                last_sent_at = state.get("last_sent_at")
                should_send = False
                decision_reason = "below_threshold"

                if not is_triggered:
                    self._runtime_state[symbol] = {
                        "above_threshold": False,
                        "last_quote_time": quote_time,
                        "last_threshold": threshold,
                        "last_rate": premium_rate,
                        "last_sent_at": last_sent_at,
                    }
                    decision_logs.append(
                        {
                            "symbol": symbol,
                            "contract_code": contract_code or "--",
                            "premium_rate": premium_rate,
                            "threshold": threshold,
                            "triggered": False,
                            "should_send": False,
                            "reason": decision_reason,
                            "quote_time": quote_time,
                            "last_sent_at": last_sent_at,
                        }
                    )
                    continue

                should_send = not state.get("above_threshold", False)
                if should_send:
                    decision_reason = "threshold_crossed"
                if not should_send:
                    same_tick = (
                        state.get("last_quote_time") == quote_time
                        and _to_float(state.get("last_threshold"), threshold) == threshold
                    )
                    if same_tick:
                        decision_reason = "same_quote_time"
                    elif not isinstance(last_sent_at, datetime):
                        should_send = True
                        decision_reason = "retry_after_unsent_attempt"
                    elif cooldown == timedelta(0):
                        should_send = True
                        decision_reason = "cooldown_disabled"
                    elif (now - last_sent_at) >= cooldown:
                        should_send = True
                        decision_reason = "cooldown_elapsed"
                    else:
                        remaining_seconds = max(int((cooldown - (now - last_sent_at)).total_seconds()), 0)
                        decision_reason = f"cooldown_active_{remaining_seconds}s"

                self._runtime_state[symbol] = {
                    "above_threshold": True,
                    "last_quote_time": quote_time,
                    "last_threshold": threshold,
                    "last_rate": premium_rate,
                    "last_sent_at": last_sent_at,
                }

                decision_logs.append(
                    {
                        "symbol": symbol,
                        "contract_code": contract_code or "--",
                        "premium_rate": premium_rate,
                        "threshold": threshold,
                        "triggered": True,
                        "should_send": should_send,
                        "reason": decision_reason,
                        "quote_time": quote_time,
                        "last_sent_at": last_sent_at,
                    }
                )

                if should_send:
                    event = self._build_event(snapshot, symbol, symbol_data, threshold)
                    event["_detected_at"] = now
                    event["_decision_reason"] = decision_reason
                    pending_events.append(event)

        for decision in decision_logs:
            LOGGER.info(
                "alert decision symbol=%s contract=%s rate=%+.4f threshold=%.4f triggered=%s should_send=%s reason=%s quote_time=%s last_sent_at=%s",
                decision["symbol"],
                decision["contract_code"],
                decision["premium_rate"],
                decision["threshold"],
                decision["triggered"],
                decision["should_send"],
                decision["reason"],
                decision["quote_time"] or "-",
                _format_log_time(decision["last_sent_at"]),
            )

        results: List[Dict[str, Any]] = []
        for event in pending_events:
            deliveries = self._dispatch_event(event, config)
            if any(item.get("status") == "sent" for item in deliveries):
                with self._lock:
                    state = self._runtime_state.get(event["symbol"])
                    if state:
                        state["last_sent_at"] = event["_detected_at"]
            LOGGER.info(
                "alert dispatch symbol=%s contract=%s reason=%s deliveries=%s",
                event["symbol"],
                event["contract_code"],
                event.get("_decision_reason", "-"),
                _delivery_summary(deliveries),
            )
            results.append(
                {
                    "symbol": event["symbol"],
                    "contract_code": event["contract_code"],
                    "quote_time": event["quote_time"],
                    "premium_rate": event["premium_rate"],
                    "threshold": event["threshold"],
                    "deliveries": deliveries,
                }
            )
        LOGGER.info(
            "alert evaluation complete pending=%s dispatched=%s",
            len(pending_events),
            len(results),
        )
        return results

    def send_test_notification(self) -> Dict[str, Any]:
        config = self.get_config()
        event = {
            "symbol": "TEST",
            "symbol_name": "测试通知",
            "contract_code": "TEST0000",
            "quote_time": _now().strftime("%Y-%m-%d %H:%M:%S"),
            "premium_rate": config.get("trigger_threshold", DEFAULT_ALERT_CONFIG["trigger_threshold"]),
            "premium_points": 12.34,
            "threshold": config.get("trigger_threshold", DEFAULT_ALERT_CONFIG["trigger_threshold"]),
            "quality": "ok",
            "quality_reason": "manual test",
            "generated_at": _now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return {
            "success": True,
            "results": self._dispatch_event(event, config, is_test=True),
        }

    def _sanitize_config(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        merged = _deep_merge(DEFAULT_ALERT_CONFIG, raw or {})
        email = merged.get("email") or {}
        feishu = merged.get("feishu") or {}
        wecom = merged.get("wecom") or {}

        security = str(email.get("security") or "ssl").strip().lower()
        if security not in {"ssl", "starttls", "none"}:
            security = "ssl"

        return {
            "trigger_threshold": round(abs(_to_float(merged.get("trigger_threshold"), 2.0)), 4),
            "cooldown_minutes": max(_to_int(merged.get("cooldown_minutes"), 10), 0),
            "popup_enabled": _to_bool(merged.get("popup_enabled"), True),
            "email": {
                "enabled": _to_bool(email.get("enabled"), False),
                "smtp_host": str(email.get("smtp_host") or "").strip(),
                "smtp_port": max(_to_int(email.get("smtp_port"), 465), 1),
                "username": str(email.get("username") or "").strip(),
                "password": str(email.get("password") or ""),
                "sender": str(email.get("sender") or "").strip(),
                "recipients": str(email.get("recipients") or "").strip(),
                "security": security,
                "subject_prefix": str(email.get("subject_prefix") or "[升贴水提醒]").strip() or "[升贴水提醒]",
            },
            "feishu": {
                "enabled": _to_bool(feishu.get("enabled"), False),
                "webhook_url": str(feishu.get("webhook_url") or "").strip(),
                "secret": str(feishu.get("secret") or "").strip(),
            },
            "wecom": {
                "enabled": _to_bool(wecom.get("enabled"), False),
                "webhook_url": str(wecom.get("webhook_url") or "").strip(),
            },
        }

    def _build_event(
        self,
        snapshot: Dict[str, Any],
        symbol: str,
        symbol_data: Dict[str, Any],
        threshold: float,
    ) -> Dict[str, Any]:
        main_contract = symbol_data.get("main_contract") or {}
        return {
            "symbol": symbol,
            "symbol_name": symbol_data.get("symbol_name") or symbol,
            "contract_code": main_contract.get("contract_code") or "--",
            "quote_time": main_contract.get("quote_time") or snapshot.get("generated_at") or _now().strftime("%Y-%m-%d %H:%M:%S"),
            "premium_rate": round(_to_float(main_contract.get("premium_rate"), 0.0), 4),
            "premium_points": round(_to_float(main_contract.get("premium_points"), 0.0), 4),
            "threshold": round(threshold, 4),
            "quality": main_contract.get("data_quality") or "ok",
            "quality_reason": main_contract.get("quality_reason") or "",
            "generated_at": snapshot.get("generated_at") or _now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _dispatch_event(
        self,
        event: Dict[str, Any],
        config: Dict[str, Any],
        is_test: bool = False,
    ) -> List[Dict[str, Any]]:
        message = self._compose_message(event, is_test=is_test)
        title_prefix = config.get("email", {}).get("subject_prefix") or "[升贴水提醒]"
        title = f"{title_prefix} {event['symbol']} {event['contract_code']}"
        results = [
            self._send_email(config.get("email") or {}, title, message),
            self._send_feishu(config.get("feishu") or {}, message),
            self._send_wecom(config.get("wecom") or {}, message),
        ]
        return results

    def _config_summary(self, config: Dict[str, Any]) -> str:
        email_config = config.get("email") or {}
        recipients = [
            item.strip()
            for item in str(email_config.get("recipients") or "").replace(";", ",").split(",")
            if item.strip()
        ]
        return (
            f"trigger_threshold={config.get('trigger_threshold')} "
            f"cooldown_minutes={config.get('cooldown_minutes')} "
            f"popup_enabled={config.get('popup_enabled')} "
            f"email_enabled={email_config.get('enabled')} "
            f"smtp_host={email_config.get('smtp_host') or '-'} "
            f"smtp_port={email_config.get('smtp_port')} "
            f"sender={email_config.get('sender') or '-'} "
            f"recipients={len(recipients)} "
            f"feishu_enabled={(config.get('feishu') or {}).get('enabled')} "
            f"wecom_enabled={(config.get('wecom') or {}).get('enabled')}"
        )

    def _compose_message(self, event: Dict[str, Any], is_test: bool = False) -> str:
        test_prefix = "[测试通知]\n" if is_test else ""
        quality_reason = event.get("quality_reason") or "无"
        return (
            f"{test_prefix}"
            f"时间: {event['quote_time']}\n"
            f"品种: {event['symbol']} {event['symbol_name']}\n"
            f"主力合约: {event['contract_code']}\n"
            f"升贴水率: {event['premium_rate']:+.3f}%\n"
            f"升贴水点数: {event['premium_points']:+.2f}\n"
            f"触发阈值: ±{event['threshold']:.3f}%\n"
            f"数据质量: {event['quality']}\n"
            f"质量说明: {quality_reason}\n"
            f"生成时间: {event['generated_at']}"
        )

    def _send_email(self, config: Dict[str, Any], title: str, message: str) -> Dict[str, Any]:
        if not config.get("enabled"):
            return {"channel": "email", "status": "disabled", "detail": "未启用"}

        required = ["smtp_host", "sender", "recipients"]
        missing = [field for field in required if not str(config.get(field) or "").strip()]
        if missing:
            return {
                "channel": "email",
                "status": "error",
                "detail": f"缺少配置: {', '.join(missing)}",
            }

        recipients = [
            item.strip()
            for item in str(config.get("recipients") or "").replace(";", ",").split(",")
            if item.strip()
        ]
        if not recipients:
            return {"channel": "email", "status": "error", "detail": "收件人为空"}

        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = config.get("sender")
        msg["To"] = ", ".join(recipients)
        msg.set_content(message)

        security = config.get("security") or "ssl"
        LOGGER.info(
            "email send start host=%s port=%s sender=%s recipients=%s security=%s subject=%s",
            config.get("smtp_host") or "-",
            config.get("smtp_port"),
            config.get("sender") or "-",
            len(recipients),
            security,
            title,
        )
        try:
            if security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    config.get("smtp_host"),
                    _to_int(config.get("smtp_port"), 465),
                    timeout=10,
                )
            else:
                server = smtplib.SMTP(
                    config.get("smtp_host"),
                    _to_int(config.get("smtp_port"), 25),
                    timeout=10,
                )
            with server:
                if security == "starttls":
                    server.starttls()
                if config.get("username"):
                    server.login(config.get("username"), config.get("password") or "")
                server.send_message(msg)
        except Exception as exc:
            LOGGER.warning("email notification failed: %s", exc)
            return {"channel": "email", "status": "error", "detail": str(exc)}

        LOGGER.info(
            "email send success sender=%s recipients=%s subject=%s",
            config.get("sender") or "-",
            len(recipients),
            title,
        )
        return {
            "channel": "email",
            "status": "sent",
            "detail": f"已发送到 {', '.join(recipients)}",
        }

    def _send_feishu(self, config: Dict[str, Any], message: str) -> Dict[str, Any]:
        if not config.get("enabled"):
            return {"channel": "feishu", "status": "disabled", "detail": "未启用"}
        webhook_url = str(config.get("webhook_url") or "").strip()
        if not webhook_url:
            return {"channel": "feishu", "status": "error", "detail": "缺少 webhook_url"}

        payload: Dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": message},
        }
        secret = str(config.get("secret") or "").strip()
        if secret:
            timestamp = str(int(_now().timestamp()))
            string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
            sign = base64.b64encode(
                hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
            ).decode("utf-8")
            payload["timestamp"] = timestamp
            payload["sign"] = sign

        return self._post_json("feishu", webhook_url, payload)

    def _send_wecom(self, config: Dict[str, Any], message: str) -> Dict[str, Any]:
        if not config.get("enabled"):
            return {"channel": "wecom", "status": "disabled", "detail": "未启用"}
        webhook_url = str(config.get("webhook_url") or "").strip()
        if not webhook_url:
            return {"channel": "wecom", "status": "error", "detail": "缺少 webhook_url"}

        payload = {
            "msgtype": "text",
            "text": {"content": message},
        }
        return self._post_json("wecom", webhook_url, payload)

    def _post_json(self, channel: str, webhook_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        parsed = urlparse(webhook_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"channel": channel, "status": "error", "detail": "webhook_url 非法"}
        LOGGER.info("%s send start webhook=%s", channel, parsed.netloc)
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as exc:
            LOGGER.warning("%s notification failed: %s", channel, exc)
            return {"channel": channel, "status": "error", "detail": str(exc)}

        detail = response.text.strip()
        try:
            response_data = response.json()
        except ValueError:
            response_data = None

        if isinstance(response_data, dict):
            if "errcode" in response_data and _to_int(response_data.get("errcode"), 0) != 0:
                return {
                    "channel": channel,
                    "status": "error",
                    "detail": json.dumps(response_data, ensure_ascii=False),
                }
            if "StatusCode" in response_data and _to_int(response_data.get("StatusCode"), 0) != 0:
                return {
                    "channel": channel,
                    "status": "error",
                    "detail": json.dumps(response_data, ensure_ascii=False),
                }
            if "code" in response_data and _to_int(response_data.get("code"), 0) not in {0, 200}:
                return {
                    "channel": channel,
                    "status": "error",
                    "detail": json.dumps(response_data, ensure_ascii=False),
                }
            detail = json.dumps(response_data, ensure_ascii=False)

        if len(detail) > 200:
            detail = detail[:200]
        LOGGER.info("%s send success webhook=%s detail=%s", channel, parsed.netloc, detail or "ok")
        return {
            "channel": channel,
            "status": "sent",
            "detail": detail or "ok",
        }

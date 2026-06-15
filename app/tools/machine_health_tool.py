"""
设备健康预测工具：调用工业健康预测 API 对传感器数据进行质量/风险预测。
"""

from __future__ import annotations

import json
from typing import Any

import requests

from config import HEALTH_API_URL, HEALTH_API_TIMEOUT


def _format_probabilities(probabilities: Any) -> str:
    if not isinstance(probabilities, dict) or not probabilities:
        return "（无）"

    lines = []
    for label, prob in probabilities.items():
        if isinstance(prob, (int, float)):
            lines.append(f"- {label}: {prob:.2%}")
        else:
            lines.append(f"- {label}: {prob}")
    return "\n".join(lines)


def check_machine_health_tool(sensor_data: dict) -> str:
    """
    根据传感器数据调用 HEALTH_API_URL/predict，返回设备健康预测结果。
    """
    if not sensor_data:
        return "⚠️ 传感器数据为空，请提供有效的 sensor_data 字典。"

    url = f"{HEALTH_API_URL.rstrip('/')}/predict"
    try:
        response = requests.post(
            url,
            json={"features": sensor_data},
            timeout=HEALTH_API_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout:
        return f"⚠️ 设备健康预测请求超时，请确认服务可用：{url}"
    except requests.ConnectionError:
        return (
            f"⚠️ 无法连接设备健康预测 API，请确认 HEALTH_API_URL 正确且服务已启动："
            f"{HEALTH_API_URL}"
        )
    except requests.HTTPError as exc:
        detail = ""
        if exc.response is not None:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                detail = exc.response.text
        status = exc.response.status_code if exc.response is not None else "unknown"
        return f"⚠️ 设备健康预测失败（HTTP {status}）：{detail}"
    except requests.RequestException as exc:
        return f"⚠️ 设备健康预测时发生网络错误：{exc}"

    prediction = payload.get("prediction")
    risk_level = payload.get("risk_level")
    recommendation = payload.get("recommendation")
    probabilities = payload.get("probabilities")

    lines = [
        "## 设备健康预测结果",
        f"prediction: {prediction if prediction is not None else '（无）'}",
        f"risk_level: {risk_level if risk_level is not None else '（无）'}",
        "recommendation:",
        str(recommendation) if recommendation else "（无）",
        "probabilities:",
        _format_probabilities(probabilities),
        "",
        "raw_response:",
        json.dumps(
            {
                "prediction": prediction,
                "risk_level": risk_level,
                "recommendation": recommendation,
                "probabilities": probabilities,
            },
            ensure_ascii=False,
        ),
    ]
    return "\n".join(lines)

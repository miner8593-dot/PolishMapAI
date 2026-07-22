from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class AiSettings:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    timeout: int = 90
    system_prompt: str = (
        "You are a cartographic extraction engine. Return only a GeoJSON FeatureCollection. "
        "Every feature must include confidence (0..1) and source properties."
    )


def validate_geojson(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise ValueError("AI response is not a GeoJSON FeatureCollection")
    features = value.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoJSON features must be an array")
    allowed = {"Point", "LineString", "Polygon"}
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Invalid GeoJSON feature")
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in allowed or "coordinates" not in geometry:
            raise ValueError("Only Point, LineString and Polygon are supported")
        props = feature.setdefault("properties", {})
        confidence = props.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
    return value


def request_features(settings: AiSettings, api_key: str, task: str, context: dict) -> tuple[dict, dict]:
    schema_hint = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"confidence": 0.8, "label": ""}, "geometry": {"type": "Polygon", "coordinates": []}}]}
    content = json.dumps({"task": task, "context": context, "required_output": schema_hint}, ensure_ascii=False)
    payload = {"model": settings.model, "temperature": 0, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": settings.system_prompt}, {"role": "user", "content": content}]}
    request = urllib.request.Request(
        settings.base_url.rstrip("/") + "/chat/completions",
        json.dumps(payload).encode("utf-8"),
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=settings.timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    message = result["choices"][0]["message"]["content"]
    geojson = validate_geojson(json.loads(message))
    audit = {"source": settings.base_url, "model": settings.model, "time": started,
             "feature_count": len(geojson["features"]), "task": task}
    return geojson, audit


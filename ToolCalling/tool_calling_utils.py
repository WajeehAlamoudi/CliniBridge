import datetime
import decimal
import json


def serialize_result(data):
    if isinstance(data, list):
        return [serialize_result(item) for item in data]

    if isinstance(data, dict):
        return {key: serialize_result(value) for key, value in data.items()}

    if isinstance(data, (datetime.date, datetime.datetime)):
        return data.isoformat()

    if isinstance(data, datetime.timedelta):
        return str(data)

    if isinstance(data, decimal.Decimal):
        return float(data)

    if isinstance(data, set):
        return [serialize_result(item) for item in data]

    if hasattr(data, "__dict__"):
        return serialize_result(data.__dict__)

    try:
        json.dumps(data)
        return data
    except Exception:
        return str(data)

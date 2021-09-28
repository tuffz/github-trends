import logging
import io

from datetime import datetime, date, timedelta
from functools import wraps
from typing import Any, Callable, Dict, List, Tuple

from fastapi import Response, status

from svgwrite.drawing import Drawing  # type: ignore

from src.svg.error import get_error_svg


def fail_gracefully(func: Callable[..., Any]):
    @wraps(func)  # needed to play nice with FastAPI decorator
    def wrapper(response: Response, *args: List[Any], **kwargs: Dict[str, Any]) -> Any:
        start = datetime.now()
        try:
            data = func(response, *args, **kwargs)
            return {"data": data, "message": "200 OK", "time": datetime.now() - start}
        except Exception as e:
            logging.exception(e)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return {
                "data": [],
                "message": "Error " + str(e),
                "time": datetime.now() - start,
            }

    return wrapper


def async_fail_gracefully(func: Callable[..., Any]):
    @wraps(func)  # needed to play nice with FastAPI decorator
    async def wrapper(
        response: Response, *args: List[Any], **kwargs: Dict[str, Any]
    ) -> Any:
        start = datetime.now()
        try:
            data = await func(response, *args, **kwargs)
            return {"data": data, "message": "200 OK", "time": datetime.now() - start}
        except Exception as e:
            logging.exception(e)
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return {
                "data": [],
                "message": "Error " + str(e),
                "time": datetime.now() - start,
            }

    return wrapper


# NOTE: returns HTTP_200_OK regardless to avoid retrying PubSub API
def pubsub_fail_gracefully(func: Callable[..., Any]):
    @wraps(func)  # needed to play nice with FastAPI decorator
    async def wrapper(
        response: Response, *args: List[Any], **kwargs: Dict[str, Any]
    ) -> Any:
        start = datetime.now()
        try:
            data = await func(response, *args, **kwargs)
            return {"data": data, "message": "200 OK", "time": datetime.now() - start}
        except Exception as e:
            logging.exception(e)
            response.status_code = status.HTTP_200_OK
            return {
                "data": [],
                "message": "Error " + str(e),
                "time": datetime.now() - start,
            }

    return wrapper


# NOTE: implied async, sync not implemented yet
def svg_fail_gracefully(func: Callable[..., Any]):
    @wraps(func)  # needed to play nice with FastAPI decorator
    async def wrapper(
        response: Response, *args: List[Any], **kwargs: Dict[str, Any]
    ) -> Any:
        d: Drawing
        status_code: int
        start = datetime.now()
        try:
            d = await func(response, *args, **kwargs)
            status_code = status.HTTP_200_OK
        except Exception as e:
            logging.exception(e)
            d = get_error_svg()
            status_code = status.HTTP_200_OK

        sio = io.StringIO()
        d.write(sio)  # type: ignore

        print(datetime.now() - start)

        return Response(
            sio.getvalue(), media_type="image/svg+xml", status_code=status_code
        )

    return wrapper


def date_to_datetime(
    dt: date, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:

    return datetime(dt.year, dt.month, dt.day, hour, minute, second)


# NOTE: return None to avoid caching
def alru_cache(max_size: int = 128, ttl: timedelta = timedelta(hours=1)):
    def decorator(func: Callable[..., Any]) -> Any:
        cache: Dict[Any, Tuple[datetime, Any]] = {}
        keys: List[Any] = []

        @wraps(func)
        async def wrapper(*args: List[Any], **kwargs: Dict[str, Any]) -> Any:
            now = datetime.now()
            key = tuple(args), frozenset(kwargs.items())
            if key not in cache or now - cache[key][0] > ttl:
                value = await func(*args, **kwargs)
                if not value:
                    return None
                cache[key] = (now, value)
                keys.append(key)
                if len(keys) > max_size:
                    del cache[keys.pop(0)]
            return cache[key][1]

        return wrapper

    return decorator

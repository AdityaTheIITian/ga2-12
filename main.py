import math
import os
import time
import uuid
from collections import deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = "23f1003148@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://app-bp1ljg.example.com"
# The page you grade from: scheme + host only, e.g. "https://something.example.com".
# Copy it from the address bar of the exam page, with no path or trailing slash.
EXAM_ORIGIN = os.environ.get("EXAM_ORIGIN", "https://CHANGE-ME.example.com")

BUCKET = 13       # requests per client per window
WINDOW = 10.0     # seconds

app = FastAPI()
windows: dict[str, deque] = {}


# Innermost: per-client rate limiter. Preflights never reach it, because CORS answers them first.
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client = request.headers.get("x-client-id")
    if client and request.method != "OPTIONS":
        now = time.monotonic()
        q = windows.setdefault(client, deque())
        while q and now - q[0] >= WINDOW:
            q.popleft()
        if len(q) >= BUCKET:
            retry = max(1, math.ceil(WINDOW - (now - q[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded", "request_id": request.state.request_id},
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
    return await call_next(request)


# Middle: scoped CORS. Exact origins only, never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, EXAM_ORIGIN],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
    expose_headers=["X-Request-ID", "Retry-After"],  # lets browser JS read these headers
)


# Outermost: request context. Runs last on the way out, so it stamps every response,
# including preflights, 429s and CORS rejections.
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id", "").strip() or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/ping")
async def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}

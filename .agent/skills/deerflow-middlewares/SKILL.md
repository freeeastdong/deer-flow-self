# DeerFlow Middleware Patterns

A comprehensive reference of middleware patterns used across the DeerFlow project (FastAPI gateway + LangChain agent runtime + Next.js frontend). Use this skill when building similar full-stack AI applications that need authentication, CSRF protection, agent safety guards, or LLM resilience patterns.

---

## 1. Architecture Overview

DeerFlow uses **three distinct middleware layers**:

| Layer | Framework | Middleware Type | Location |
|---|---|---|---|
| Gateway | FastAPI + Starlette | ASGI `BaseHTTPMiddleware` | `backend/app/gateway/` |
| Agent Runtime | LangChain | `AgentMiddleware` lifecycle hooks | `backend/packages/harness/deerflow/agents/middlewares/` |
| Frontend | Next.js + vanilla JS | Fetch interceptors + SSR guards | `frontend/src/core/api/`, `frontend/src/app/` |

**Key design principle**: Every layer is **fail-closed**. Auth rejects by default, CSRF blocks state-changing requests without tokens, sandbox audit blocks dangerous commands, and LLM errors return graceful fallback messages instead of crashing the agent loop.

---

## 2. Gateway Middleware (FastAPI / Starlette)

### 2.1 Fail-Closed Authentication Middleware

**Pattern**: `BaseHTTPMiddleware` that stamps `request.state.user` and sets a `contextvar` so downstream repository layers get owner-filtering "for free" without every route needing a decorator.

**File**: `backend/app/gateway/auth_middleware.py`

```python
from starlette.middleware.base import BaseHTTPMiddleware
from deerflow.runtime.user_context import reset_current_user, set_current_user

# Define public paths explicitly — everything else is rejected by default
_PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health", "/docs", "/redoc", "/openapi.json",
)
_PUBLIC_EXACT_PATHS: frozenset[str] = frozenset({
    "/api/v1/auth/login/local",
    "/api/v1/auth/register",
    "/api/v1/auth/logout",
    "/api/v1/auth/setup-status",
    "/api/v1/auth/initialize",
})

def _is_public(path: str) -> bool:
    stripped = path.rstrip("/")
    if stripped in _PUBLIC_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        # Support internal service-to-service tokens
        internal_user = None
        if is_valid_internal_auth_token(request.headers.get(INTERNAL_AUTH_HEADER_NAME)):
            internal_user = get_internal_user()

        # Stage 1: cookie presence check
        if internal_user is None and not request.cookies.get("access_token"):
            return JSONResponse(status_code=401, content={...})

        # Stage 2: strict JWT validation (reject expired/malformed tokens)
        if internal_user is not None:
            user = internal_user
        else:
            try:
                user = await get_current_user_from_request(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        # Stage 3: reject disabled accounts at the outermost gate
        if not user.is_active:
            return JSONResponse(status_code=403, content={...})

        # Stamp user into both request.state AND contextvar
        request.state.user = user
        request.state.auth = AuthContext(user=user, permissions=_ALL_PERMISSIONS)
        token = set_current_user(user)
        try:
            return await call_next(request)
        finally:
            reset_current_user(token)
```

**Reusable takeaways**:
1. Use `frozenset` + `tuple` for path allowlists — immutable and hash-safe.
2. Two-stage validation: cheap cookie check first, expensive JWT decode second.
3. Stamp into `request.state` **and** a `contextvar` so ORM/repository layers can access the current user without threading `request` through every function call.
4. Always use `try/finally` around `call_next()` when setting contextvars to avoid leakage between requests.

---

### 2.2 Double Submit Cookie CSRF Middleware

**Pattern**: State-changing requests must carry an `X-CSRF-Token` header that matches the `csrf_token` cookie. Auth endpoints are exempt (user doesn't have a cookie yet).

**File**: `backend/app/gateway/csrf_middleware.py`

```python
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_TOKEN_LENGTH = 64  # bytes

def is_secure_request(request: Request) -> bool:
    """Detect whether the original client request was made over HTTPS."""
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"

def generate_csrf_token() -> str:
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)

def should_check_csrf(request: Request) -> bool:
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return False
    path = request.url.path.rstrip("/")
    if path == "/api/v1/auth/me":
        return False
    return True

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        _is_auth = is_auth_endpoint(request)

        if should_check_csrf(request) and not _is_auth:
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)

            if not cookie_token or not header_token:
                return JSONResponse(status_code=403, content={...})

            if not secrets.compare_digest(cookie_token, header_token):
                return JSONResponse(status_code=403, content={...})

        response = await call_next(request)

        # Set CSRF cookie on auth POSTs (login/register)
        if _is_auth and request.method == "POST":
            csrf_token = generate_csrf_token()
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=csrf_token,
                httponly=False,   # MUST be JS-readable for Double Submit pattern
                secure=is_secure_request(request),
                samesite="strict",
            )
        return response
```

**Reusable takeaways**:
1. `httponly=False` on the CSRF cookie is **intentional** — the frontend needs to read it via JavaScript to echo it back in the header.
2. Use `secrets.compare_digest()` for constant-time comparison to prevent timing attacks.
3. Set the cookie on the **response** of successful auth POSTs, not on every request.
4. Respect `x-forwarded-proto` when behind a reverse proxy (Nginx, ALB, etc.).

---

### 2.3 Frontend Fetch Interceptor (CSRF + 401 Redirect)

**Pattern**: A thin `fetch()` wrapper that mirrors the gateway's CSRF logic and auto-redirects on 401.

**File**: `frontend/src/core/api/fetcher.ts`

```typescript
export const STATE_CHANGING_METHODS: ReadonlySet<string> = new Set(
  ["POST", "PUT", "DELETE", "PATCH"],
);

export function isStateChangingMethod(method: string): boolean {
  return STATE_CHANGING_METHODS.has(method.toUpperCase());
}

export function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  for (const pair of document.cookie.split("; ")) {
    if (pair.startsWith("csrf_token=")) {
      return decodeURIComponent(pair.slice("csrf_token=".length));
    }
  }
  return null;
}

export async function fetch(
  input: RequestInfo | string,
  init?: RequestInit,
): Promise<Response> {
  const url = typeof input === "string" ? input : input.url;

  let headers = init?.headers;
  if (isStateChangingMethod(init?.method ?? "GET")) {
    const token = readCsrfCookie();
    if (token) {
      const merged = new Headers(headers);
      if (!merged.has("X-CSRF-Token")) {
        merged.set("X-CSRF-Token", token);
      }
      headers = merged;
    }
  }

  const res = await globalThis.fetch(url, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    window.location.href = buildLoginUrl(window.location.pathname);
    throw new Error("Unauthorized");
  }
  return res;
}
```

**Reusable takeaways**:
1. Wrap `globalThis.fetch` instead of using Axios — zero dependency overhead.
2. Create a **fresh** `Headers` object so you don't mutate the caller's headers.
3. `credentials: "include"` is mandatory for HttpOnly cookies to travel cross-origin.
4. SSR-safe: check `typeof document === "undefined"` before reading cookies.

---

### 2.4 SSR Auth Guards (Next.js App Router)

**Pattern**: Server Component layouts that redirect unauthenticated users before rendering.

**File**: `frontend/src/app/workspace/layout.tsx`

```typescript
export default async function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const user = await getServerSideUser();
  if (!user) {
    redirect("/login");
  }
  if (user.needsSetup) {
    redirect("/setup");
  }
  return <AuthProvider initialUser={user}>{children}</AuthProvider>;
}
```

**Reusable takeaways**:
1. Do the auth check in a **Server Component layout** so unauthenticated users never download client JS bundles.
2. Return the user object from the server layout and pass it into a client `AuthProvider` to avoid a second client-side fetch.
3. Use inverse guards on auth pages (login/register) to redirect already-authenticated users away.

---

## 3. Agent Middleware (LangChain `AgentMiddleware`)

DeerFlow extends LangChain's `AgentMiddleware` base class, which provides lifecycle hooks:

| Hook | When | Typical Use |
|---|---|---|
| `before_agent` | Before agent starts | Directory setup, file injection |
| `after_agent` | After agent finishes | Memory queueing, cleanup |
| `before_model` | Before LLM call | Context compression, todo injection |
| `after_model` | After LLM response | Loop detection, title generation |
| `wrap_tool_call` | Around tool execution | Security audit, error wrapping |
| `wrap_model_call` | Around LLM call | Retry logic, circuit breaker |

**Important**: Always implement **both sync and async** versions of each hook (`wrap_model_call` + `awrap_model_call`, `after_model` + `aafter_model`, etc.) so the middleware works regardless of whether the runtime uses sync or async execution.

---

### 3.1 Circuit Breaker + Retry for LLM Calls

**Pattern**: Wrap LLM calls with exponential backoff retry and a circuit breaker that fast-fails after sustained errors.

**File**: `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py`

```python
class LLMErrorHandlingMiddleware(AgentMiddleware[AgentState]):
    retry_max_attempts: int = 3
    retry_base_delay_ms: int = 1000
    retry_cap_delay_ms: int = 8000

    def __init__(self, *, app_config: AppConfig, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.circuit_failure_threshold = app_config.circuit_breaker.failure_threshold
        self.circuit_recovery_timeout_sec = app_config.circuit_breaker.recovery_timeout_sec

        self._circuit_lock = threading.Lock()
        self._circuit_failure_count = 0
        self._circuit_open_until = 0.0
        self._circuit_state = "closed"   # closed → half_open → open
        self._circuit_probe_in_flight = False

    def _check_circuit(self) -> bool:
        """Returns True if circuit is OPEN (fast fail)."""
        with self._circuit_lock:
            now = time.time()
            if self._circuit_state == "open":
                if now < self._circuit_open_until:
                    return True
                self._circuit_state = "half_open"
                self._circuit_probe_in_flight = False
            if self._circuit_state == "half_open":
                if self._circuit_probe_in_flight:
                    return True
                self._circuit_probe_in_flight = True
                return False
            return False

    def _record_success(self) -> None:
        with self._circuit_lock:
            self._circuit_failure_count = 0
            self._circuit_state = "closed"
            self._circuit_probe_in_flight = False

    def _record_failure(self) -> None:
        with self._circuit_lock:
            if self._circuit_state == "half_open":
                self._circuit_open_until = time.time() + self.circuit_recovery_timeout_sec
                self._circuit_state = "open"
                self._circuit_probe_in_flight = False
                return
            self._circuit_failure_count += 1
            if self._circuit_failure_count >= self.circuit_failure_threshold:
                self._circuit_open_until = time.time() + self.circuit_recovery_timeout_sec
                self._circuit_state = "open"

    def _classify_error(self, exc: BaseException) -> tuple[bool, str]:
        """Return (is_retriable, reason). Supports English + Chinese error messages."""
        detail = str(exc).lower()
        error_code = _extract_error_code(exc)
        status_code = _extract_status_code(exc)

        # Non-retriable: quota / billing / auth
        if _matches_any(detail, _QUOTA_PATTERNS):
            return False, "quota"
        if _matches_any(detail, _AUTH_PATTERNS):
            return False, "auth"

        # Retriable: network / timeout / 5xx / busy
        if exc.__class__.__name__ in {"APITimeoutError", "APIConnectionError", "InternalServerError"}:
            return True, "transient"
        if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True, "transient"
        if _matches_any(detail, _BUSY_PATTERNS):
            return True, "busy"
        return False, "generic"

    def wrap_model_call(self, request, handler):
        if self._check_circuit():
            return AIMessage(content=self._build_circuit_breaker_message())

        attempt = 1
        while True:
            try:
                response = handler(request)
                self._record_success()
                return response
            except GraphBubbleUp:
                # NEVER swallow control-flow signals (interrupt/pause/resume)
                raise
            except Exception as exc:
                retriable, reason = self._classify_error(exc)
                if retriable and attempt < self.retry_max_attempts:
                    wait_ms = self._build_retry_delay_ms(attempt, exc)
                    self._emit_retry_event(attempt, wait_ms, reason)
                    time.sleep(wait_ms / 1000)
                    attempt += 1
                    continue
                if retriable:
                    self._record_failure()
                # Graceful fallback: return an AIMessage instead of crashing
                return AIMessage(content=self._build_user_message(exc, reason))
```

**Reusable takeaways**:
1. **Always re-raise `GraphBubbleUp`** — swallowing LangGraph control-flow signals breaks interrupt/resume.
2. Classify errors into **retriable vs non-retriable**. Quota/auth errors should fail fast; network errors should retry.
3. Return a **graceful fallback `AIMessage`** on final failure so the agent loop continues instead of crashing.
4. Emit stream events (`llm_retry`) so the frontend can show "Retrying in 2s..." to users.
5. Use `threading.Lock` around circuit breaker state (middleware instances may be shared across threads).

---

### 3.2 Loop Detection Middleware

**Pattern**: Two-layer detection to prevent agents from getting stuck in repetitive tool call cycles.

**File**: `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py`

```python
class LoopDetectionMiddleware(AgentMiddleware[AgentState]):
    def __init__(
        self,
        warn_threshold: int = 3,      # identical calls before warning
        hard_limit: int = 5,          # identical calls before forced stop
        window_size: int = 20,
        max_tracked_threads: int = 100,
        tool_freq_warn: int = 30,     # same tool type called 30 times
        tool_freq_hard_limit: int = 50,
    ):
        super().__init__()
        self._lock = threading.Lock()
        # OrderedDict for LRU eviction of thread tracking state
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        self._warned: dict[str, set[str]] = defaultdict(set)
        self._tool_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._tool_freq_warned: dict[str, set[str]] = defaultdict(set)

    def _hash_tool_calls(self, tool_calls: list[dict]) -> str:
        """Deterministic hash of tool call names + normalized args."""
        normalized = []
        for tc in tool_calls:
            name = tc.get("name", "")
            args, fallback = self._normalize_tool_call_args(tc.get("args", {}))
            key = self._stable_tool_key(name, args, fallback)
            normalized.append(f"{name}:{key}")
        normalized.sort()
        blob = json.dumps(normalized, sort_keys=True, default=str)
        return hashlib.md5(blob.encode()).hexdigest()[:12]

    def _apply(self, state, runtime):
        warning, hard_stop = self._track_and_check(state, runtime)

        if hard_stop:
            # Strip tool_calls from AIMessage to force text output
            messages = state.get("messages", [])
            last_msg = messages[-1]
            content = self._append_text(last_msg.content, warning)
            stripped = last_msg.model_copy(update=self._build_hard_stop_update(last_msg, content))
            return {"messages": [stripped]}

        if warning:
            # Inject as HumanMessage (not SystemMessage) to avoid Anthropic
            # "multiple non-consecutive system messages" errors.
            return {"messages": [HumanMessage(content=warning, name="loop_warning")]}

        return None

    @override
    def after_model(self, state, runtime):
        return self._apply(state, runtime)
```

**Reusable takeaways**:
1. **Hash-based detection**: catches identical tool call sets (same args).
2. **Frequency-based detection**: catches the same tool type called repeatedly with varying args (e.g. `read_file` on 40 different files).
3. On hard stop, **strip `tool_calls`** from the `AIMessage` and change `finish_reason` to `"stop"` so the model is forced to produce a final answer.
4. Inject warnings as `HumanMessage`, not `SystemMessage` — Anthropic models crash on mid-conversation system messages.
5. Use per-thread LRU eviction to prevent unbounded memory growth in long-running servers.

---

### 3.3 Sandbox Security Audit Middleware

**Pattern**: Intercept `bash` tool calls, classify commands by risk level (block / warn / pass), and either block execution or append warnings to results.

**File**: `backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py`

```python
_HIGH_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-[^\s]*r[^\s]*\s+(/\*?|~/?\*?|/home\b|/root\b)\s*$"),
    re.compile(r"dd\s+if="),
    re.compile(r"mkfs"),
    re.compile(r"\|\s*(ba)?sh\b"),           # pipe to shell
    re.compile(r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)"),
    re.compile(r"base64\s+.*-d.*\|"),
    re.compile(r">+\s*(/usr/bin/|/bin/|/sbin/)"),
    re.compile(r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*="),
    re.compile(r"/dev/tcp/"),
    re.compile(r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&"),  # fork bomb
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chmod\s+777"),
    re.compile(r"pip3?\s+install"),
    re.compile(r"apt(-get)?\s+install"),
    re.compile(r"\b(sudo|su)\b"),
    re.compile(r"\bPATH\s*="),
]

def _split_compound_command(command: str) -> list[str]:
    """Split compound commands (quote-aware) on ; && ||."""
    # ... see full implementation for quote-aware parsing ...

def _classify_command(command: str) -> str:
    # Pass 1: whole-command scan catches multi-statement attacks
    normalized = " ".join(command.split())
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    # Pass 2: per-sub-command classification
    sub_commands = _split_compound_command(command)
    worst = "pass"
    for sub in sub_commands:
        verdict = _classify_single_command(sub)
        if verdict == "block":
            return "block"
        if verdict == "warn":
            worst = "warn"
    return worst

class SandboxAuditMiddleware(AgentMiddleware[ThreadState]):
    _MAX_COMMAND_LENGTH = 10_000

    def _validate_input(self, command: str) -> str | None:
        if not command.strip():
            return "empty command"
        if len(command) > self._MAX_COMMAND_LENGTH:
            return "command too long"
        if "\x00" in command:
            return "null byte detected"
        return None

    def wrap_tool_call(self, request, handler):
        if request.tool_call.get("name") != "bash":
            return handler(request)

        command, thread_id, verdict, reject_reason = self._pre_process(request)
        if verdict == "block":
            reason = reject_reason or "security violation detected"
            return self._build_block_message(request, reason)

        result = handler(request)
        if verdict == "warn":
            result = self._append_warn_to_result(result, command)
        return result
```

**Reusable takeaways**:
1. **Two-pass classification**: whole-command scan first (catches fork bombs that span statements), then per-sub-command.
2. **Quote-aware parsing**: `shlex.split` fails on unclosed quotes; implement a custom tokenizer that fails closed.
3. Input sanitization comes **before** regex analysis: max length (10K), null byte checks, empty command checks.
4. Blocked commands return an error `ToolMessage` with `status="error"` so the agent loop continues gracefully.
5. Medium-risk commands execute normally but append a warning to the result so the LLM is informed.

---

### 3.4 Dangling Tool Call Middleware

**Pattern**: Detect `AIMessage`s with `tool_calls` that lack corresponding `ToolMessage`s (e.g. from user interruption) and inject synthetic error `ToolMessage`s at the correct position.

**File**: `backend/packages/harness/deerflow/agents/middlewares/dangling_tool_call_middleware.py`

**Use case**: When a user interrupts an agent mid-tool-execution, the next resume will have an `AIMessage` requesting tool calls but no `ToolMessage` responses. This middleware detects the mismatch and injects synthetic error messages so the LLM can continue.

---

### 3.5 Tool Error Handling Middleware

**Pattern**: Catch tool execution exceptions and convert them into error `ToolMessage`s so the agent loop continues gracefully.

**File**: `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`

**Key detail**: Preserves `GraphBubbleUp` control-flow signals — if a tool intentionally raises a bubble-up exception, it must propagate unmodified.

---

### 3.6 Summarization Middleware

**Pattern**: Extend LangChain's `SummarizationMiddleware` with "skill rescue" — preserves recently-loaded skill file read tool calls during summarization so the agent doesn't lose context about which files it just read.

**File**: `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py`

---

### 3.7 Todo Middleware

**Pattern**: Track the agent's todo list and detect two failure modes:
1. **Context loss**: When `write_todos` scrolls out of the context window, re-inject todo reminders.
2. **Premature exit**: When incomplete todos exist but no tool calls are made, force the agent back to the model.

**File**: `backend/packages/harness/deerflow/agents/middlewares/todo_middleware.py`

---

### 3.8 Memory Middleware

**Pattern**: After agent execution completes, queue the conversation for async memory update. Filters to user + assistant messages only, detects corrections vs reinforcements, and uses debounced queue + LLM summarization.

**File**: `backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py`

---

### 3.9 Middleware Assembly Pattern

**Pattern**: Factory functions assemble middleware chains in a specific order.

**File**: `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`

```python
def build_lead_runtime_middlewares() -> list[AgentMiddleware]:
    """Base runtime middlewares shared by lead and subagents."""
    return [
        ThreadDataMiddleware(),
        UploadsMiddleware(),
        SandboxMiddleware(),
        DanglingToolCallMiddleware(),
        GuardrailMiddleware(),
        ToolErrorHandlingMiddleware(),
    ]

def build_subagent_runtime_middlewares() -> list[AgentMiddleware]:
    """Subagent-specific chain (excludes uploads, includes vision conditionally)."""
    base = build_lead_runtime_middlewares()
    # ... append subagent-specific middlewares ...
    return base
```

**Typical lead agent order**:
1. `ThreadDataMiddleware` — directory setup
2. `UploadsMiddleware` — file injection
3. `SandboxMiddleware` — sandbox acquisition
4. `DanglingToolCallMiddleware` — message patching
5. `GuardrailMiddleware` — policy enforcement
6. `ToolErrorHandlingMiddleware` — tool exception wrapping
7. `DeerFlowSummarizationMiddleware` — context compression
8. `TodoMiddleware` — task tracking
9. `TitleMiddleware` — auto-title generation
10. `MemoryMiddleware` — memory queueing
11. `ViewImageMiddleware` — image injection
12. `SubagentLimitMiddleware` — concurrency limiting
13. `LoopDetectionMiddleware` — repetition breaking
14. `ClarificationMiddleware` — user clarification (**always last**)
15. `TokenUsageMiddleware` — usage logging
16. `LLMErrorHandlingMiddleware` — LLM retry/circuit breaker
17. `SandboxAuditMiddleware` — bash security audit

**Reusable takeaways**:
1. **Hard invariant**: `ClarificationMiddleware` must always be last so user-facing clarifications aren't swallowed by downstream middleware.
2. Separate **runtime middlewares** (error handling, sandbox, data) from **feature middlewares** (todos, memory, titles) so subagents can reuse the runtime base.
3. Use factory functions instead of inline lists so the same base chain can be extended for different agent types.

---

## 4. Middleware Design Checklist

When implementing new middleware in a similar project, verify:

- [ ] **Fail-closed by default** — reject/block unless explicitly allowed.
- [ ] **Both sync + async hooks** — implement `wrap_model_call` AND `awrap_model_call`.
- [ ] **Preserve control-flow signals** — never swallow `GraphBubbleUp`, `Command`, or similar framework exceptions.
- [ ] **Graceful degradation** — return fallback messages instead of crashing the agent loop.
- [ ] **Thread-safe state** — use `threading.Lock` for shared mutable state.
- [ ] **Bounded memory** — use LRU eviction or TTL for per-thread/per-request tracking.
- [ ] **Structured logging** — emit JSON audit logs for security-relevant events.
- [ ] **Stream events** — emit events (`llm_retry`, `tool_audit`, etc.) so the UI can show real-time status.
- [ ] **Contextvar propagation** — stamp auth/user info into both `request.state` and a `contextvar` for downstream automatic filtering.

---

## 5. File Reference

| Middleware | File |
|---|---|
| Auth (Gateway) | `backend/app/gateway/auth_middleware.py` |
| CSRF (Gateway) | `backend/app/gateway/csrf_middleware.py` |
| CORS (Gateway) | `backend/app/gateway/app.py` |
| AuthZ decorators | `backend/app/gateway/authz.py` |
| LangGraph Auth | `backend/app/gateway/langgraph_auth.py` |
| Fetch Interceptor | `frontend/src/core/api/fetcher.ts` |
| SSR Auth Guards | `frontend/src/app/workspace/layout.tsx`, `frontend/src/app/admin/layout.tsx`, `frontend/src/app/(auth)/layout.tsx` |
| Clarification | `backend/packages/harness/deerflow/agents/middlewares/clarification_middleware.py` |
| Dangling Tool Call | `backend/packages/harness/deerflow/agents/middlewares/dangling_tool_call_middleware.py` |
| Deferred Tool Filter | `backend/packages/harness/deerflow/agents/middlewares/deferred_tool_filter_middleware.py` |
| LLM Error Handling | `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py` |
| Loop Detection | `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py` |
| Memory | `backend/packages/harness/deerflow/agents/middlewares/memory_middleware.py` |
| Sandbox Audit | `backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py` |
| Subagent Limit | `backend/packages/harness/deerflow/agents/middlewares/subagent_limit_middleware.py` |
| Summarization | `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py` |
| Thread Data | `backend/packages/harness/deerflow/agents/middlewares/thread_data_middleware.py` |
| Title | `backend/packages/harness/deerflow/agents/middlewares/title_middleware.py` |
| Todo | `backend/packages/harness/deerflow/agents/middlewares/todo_middleware.py` |
| Token Usage | `backend/packages/harness/deerflow/agents/middlewares/token_usage_middleware.py` |
| Tool Error Handling | `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py` |
| Uploads | `backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py` |
| View Image | `backend/packages/harness/deerflow/agents/middlewares/view_image_middleware.py` |
| Guardrails | `backend/packages/harness/deerflow/guardrails/middleware.py` |
| Sandbox Lifecycle | `backend/packages/harness/deerflow/sandbox/middleware.py` |

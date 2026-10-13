"""Business logic. Services orchestrate the runtime (``SessionManager``) and repositories, and
raise ``core.errors`` instead of HTTP exceptions so they can be used outside a request."""

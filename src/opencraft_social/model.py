class PolicyError(RuntimeError):
    """Raised when a requested UX transition would violate an OpenCraft invariant."""

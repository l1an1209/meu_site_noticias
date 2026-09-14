from contextvars import ContextVar

_current_portal = ContextVar('current_portal', default=None)
_request_bound = ContextVar('tenant_request_bound', default=False)


def bind_request_tenant():
    _request_bound.set(True)


def set_current_portal(portal):
    _current_portal.set(portal)


def get_current_portal():
    return _current_portal.get()


def is_request_bound():
    return bool(_request_bound.get())


def clear_tenant_context():
    _current_portal.set(None)
    _request_bound.set(False)

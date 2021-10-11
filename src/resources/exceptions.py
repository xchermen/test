class BloxlinkException(Exception):
    def __init__(self, message=None, type="error", dm=False, hidden=False):
        self.type = type
        self.dm = dm # only implemented in a few places
        self.hidden = hidden
        self.message = message


class CancelCommand(BloxlinkException):
    pass

class Messages(CancelCommand):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)

class Message(Messages):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)

class Error(Messages):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)

class CancelledPrompt(CancelCommand):
    def __init__(self, *args, type="send", **kwargs):
        super().__init__(*args, type=type, **kwargs)


class PermissionError(BloxlinkException):
    pass

class BadUsage(BloxlinkException):
    pass

class RobloxAPIError(BloxlinkException):
    pass

class RobloxNotFound(BloxlinkException):
    pass

class RobloxDown(BloxlinkException):
    pass

class UserNotVerified(BloxlinkException):
    pass

class BloxlinkBypass(BloxlinkException):
    pass

class Blacklisted(BloxlinkException):
    pass

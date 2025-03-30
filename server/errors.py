class BaseError(Exception):
    def __init__(self, session: str):
        self.session = session
        super().__init__(self.session)


class NoCapacityError(BaseError):
    def __init__(self, session):
        super().__init__(session)
        self.message = "No capacity"


class UnknownServerError(BaseError):
    def __init__(self, session: str):
        super().__init__(session)
        self.message = "Unknown server"


class SessionInputInactivity(BaseError):
    def __init__(self, session):
        super().__init__(session)
        self.message = "Session input inactivity"


class SessionOutputInactivity(BaseError):
    def __init__(self, session):
        super().__init__(session)
        self.message = "Session ouput inactivity"

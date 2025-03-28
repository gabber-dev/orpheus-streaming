from .proto_generated.health_pb2 import ServerHealth


class Health:
    def __init__(self):
        self.routes = {}

    async def query_available_servers(self) -> list[ServerHealth]:
        return []

    async def report_status(self):
        pass

    async def get_local_server(self) -> ServerHealth:
        return ServerHealth()

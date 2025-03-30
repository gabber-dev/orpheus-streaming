from dataclasses import dataclass


@dataclass
class Config:
    public_listen_ip: str
    public_listen_port: int
    internal_connection_base_url: str
    internal_listen_ip: str
    internal_listen_port: int
    max_sessions: int
    redis_config: "RedisConfig"


@dataclass
class RedisConfig:
    host: str
    port: int
    db: int

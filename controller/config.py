from dataclasses import dataclass


@dataclass
class Config:
    listen_ip: str
    listen_port: int

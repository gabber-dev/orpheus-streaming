from dataclasses import dataclass


@dataclass
class Config:
    listen_ip: str
    listen_port: int
    advertise_url: str
    max_sessions: int
    session_input_timeout: float
    session_output_timeout: float
    controller_url: str | None
    password: str | None

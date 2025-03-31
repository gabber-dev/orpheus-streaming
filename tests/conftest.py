def pytest_configure(config):
    config.addinivalue_line(
        "markers", "redis_db(db): specify the Redis database number for the test"
    )
    config.addinivalue_line(
        "markers", "server_config(max_sessions_list, base_port): specify server config"
    )

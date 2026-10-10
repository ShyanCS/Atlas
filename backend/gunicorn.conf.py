"""One small threaded worker; no provider URL/header access logs."""

import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', '10000'))}"
workers = 1
worker_class = "gthread"
threads = 2
timeout = 180
graceful_timeout = 30
keepalive = 2
max_requests = 200
max_requests_jitter = 20
accesslog = None
errorlog = "-"
capture_output = False
limit_request_line = 4094
limit_request_fields = 40
limit_request_field_size = 4094

# utils/rate_limiter.py
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id):
        now = time.time()
        user_requests = self.requests[user_id]
        user_requests = [t for t in user_requests if now - t < self.window_seconds]
        self.requests[user_id] = user_requests
        if len(user_requests) >= self.max_requests:
            return False
        user_requests.append(now)
        return True
    
    def time_until_reset(self, user_id):
        user_requests = self.requests[user_id]
        if not user_requests:
            return 0
        oldest = min(user_requests)
        return max(0, self.window_seconds - (time.time() - oldest))

mass_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

# proxy_manager.py
import random
import os
import requests
import time
import concurrent.futures
from logger import log_error

class ProxyManager:
    def __init__(self, proxy_file='data/proxies.txt'):
        self.proxy_file = proxy_file
        self.proxies = []
        self.working_proxies = []
        self.dead_proxies = []
        self.current_index = 0
        self.load_proxies()
    
    def load_proxies(self):
        try:
            os.makedirs('data', exist_ok=True)
            if os.path.exists(self.proxy_file):
                with open(self.proxy_file, 'r') as f:
                    self.proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                print(f"✅ Loaded {len(self.proxies)} proxies")
            else:
                with open(self.proxy_file, 'w') as f:
                    f.write("# Proxy List\n# Format: ip:port or ip:port:user:pass\n")
                self.proxies = []
                print("📝 Created empty proxies.txt")
        except Exception as e:
            log_error(f"Failed to load proxies: {str(e)}")
            self.proxies = []
    
    def add_proxy(self, proxy_string):
        proxy_string = proxy_string.strip()
        if not proxy_string or proxy_string.startswith('#'):
            return False, "Invalid proxy format"
        if proxy_string in self.proxies:
            return False, "Proxy already exists"
        try:
            with open(self.proxy_file, 'a') as f:
                f.write(f"\n{proxy_string}")
            self.proxies.append(proxy_string)
            return True, f"✅ Proxy added successfully"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def add_proxies_from_text(self, text):
        lines = text.strip().split('\n')
        added = 0
        skipped = 0
        new_proxies = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if line not in self.proxies and line not in new_proxies:
                    self.proxies.append(line)
                    new_proxies.append(line)
                    added += 1
                else:
                    skipped += 1
        try:
            with open(self.proxy_file, 'a') as f:
                for proxy in new_proxies:
                    f.write(f"\n{proxy}")
        except Exception as e:
            log_error(f"Failed to save proxies: {str(e)}")
        return added, skipped
    
    def remove_proxy(self, proxy_string):
        proxy_string = proxy_string.strip()
        if proxy_string not in self.proxies:
            return False, "Proxy not found"
        self.proxies.remove(proxy_string)
        try:
            with open(self.proxy_file, 'w') as f:
                f.write("# Proxy List\n# Format: ip:port or ip:port:user:pass\n")
                for proxy in self.proxies:
                    f.write(f"{proxy}\n")
            return True, "✅ Proxy removed"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def clear_proxies(self):
        self.proxies = []
        self.working_proxies = []
        self.dead_proxies = []
        try:
            with open(self.proxy_file, 'w') as f:
                f.write("# Proxy List\n# Format: ip:port or ip:port:user:pass\n")
            return True, "✅ All proxies cleared"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def get_random_proxy(self):
        if not self.proxies:
            return None
        proxy = random.choice(self.proxies)
        return self.format_proxy(proxy)
    
    def get_next_proxy(self):
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_index % len(self.proxies)]
        self.current_index += 1
        return self.format_proxy(proxy)
    
    def format_proxy(self, proxy_string):
        parts = proxy_string.split(':')
        if len(parts) == 2:
            return {
                'http': f'http://{parts[0]}:{parts[1]}',
                'https': f'http://{parts[0]}:{parts[1]}'
            }
        elif len(parts) == 4:
            return {
                'http': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}',
                'https': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
            }
        return None
    
    def has_proxies(self):
        return len(self.proxies) > 0
    
    def count_proxies(self):
        return len(self.proxies)
    
    def get_all_proxies(self):
        return self.proxies.copy()
    
    def check_single_proxy(self, proxy_string, timeout=10):
        try:
            formatted = self.format_proxy(proxy_string)
            if not formatted:
                return proxy_string, False, "Invalid format"
            test_url = 'http://httpbin.org/ip'
            start_time = time.time()
            response = requests.get(
                test_url, 
                proxies=formatted, 
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            elapsed = time.time() - start_time
            if response.status_code == 200:
                data = response.json()
                proxy_ip = data.get('origin', 'Unknown')
                return proxy_string, True, f"Working ({elapsed:.2f}s) - IP: {proxy_ip}"
            else:
                return proxy_string, False, f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            return proxy_string, False, "Timeout"
        except requests.exceptions.ConnectionError:
            return proxy_string, False, "Connection Error"
        except requests.exceptions.ProxyError:
            return proxy_string, False, "Proxy Error"
        except Exception as e:
            return proxy_string, False, f"Error: {str(e)[:30]}"
    
    def check_all_proxies(self, callback=None, max_workers=10):
        if not self.proxies:
            return [], []
        working = []
        dead = []
        total = len(self.proxies)
        checked = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {
                executor.submit(self.check_single_proxy, proxy): proxy 
                for proxy in self.proxies
            }
            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                checked += 1
                try:
                    proxy_string, is_working, msg = future.result()
                    if is_working:
                        working.append(proxy_string)
                    else:
                        dead.append({'proxy': proxy_string, 'reason': msg})
                    if callback:
                        callback(checked, total, proxy_string, is_working, msg)
                except Exception as e:
                    dead.append({'proxy': proxy, 'reason': f'Error: {str(e)[:30]}'})
                    if callback:
                        callback(checked, total, proxy, False, f'Error: {str(e)[:30]}')
        self.working_proxies = working
        self.dead_proxies = dead
        return working, dead
    
    def save_working_proxies(self, output_file='data/working_proxies.txt'):
        try:
            with open(output_file, 'w') as f:
                f.write("# Working Proxies\n")
                for proxy in self.working_proxies:
                    f.write(f"{proxy}\n")
            return True, f"✅ Saved {len(self.working_proxies)} working proxies"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"
    
    def remove_dead_proxies(self):
        dead_proxy_strings = [item['proxy'] for item in self.dead_proxies]
        self.proxies = [p for p in self.proxies if p not in dead_proxy_strings]
        try:
            with open(self.proxy_file, 'w') as f:
                f.write("# Proxy List\n# Format: ip:port or ip:port:user:pass\n")
                for proxy in self.proxies:
                    f.write(f"{proxy}\n")
            removed_count = len(dead_proxy_strings)
            self.working_proxies = []
            self.dead_proxies = []
            return True, f"✅ Removed {removed_count} dead proxies"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"

proxy_manager = ProxyManager()

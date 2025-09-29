import logging
import json
import os
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class StatsTracker:
    def __init__(self, stats_file: str = "user_stats.json"):
        self.stats_file = stats_file
        self.stats: Dict[str, Dict[str, Any]] = self._load_stats()

    def _load_stats(self) -> Dict[str, Dict[str, Any]]:
        """Load user statistics from file"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading stats file: {e}")
                return {}
        return {}

    def _save_stats(self):
        """Save user statistics to file"""
        try:
            # Create a clean copy of stats with only serializable data
            clean_stats = {}
            for user_id, user_data in self.stats.items():
                # Debug: check what's in user_data
                if not isinstance(user_data, dict):
                    logger.warning(f"Non-dict user_data for {user_id}: {type(user_data)}")
                    continue
                
                # Clean services_used dict to ensure all keys/values are serializable
                services_used = {}
                if 'services_used' in user_data:
                    for service_key, service_count in user_data['services_used'].items():
                        if isinstance(service_key, str) and isinstance(service_count, (int, float)):
                            services_used[service_key] = service_count
                        else:
                            logger.warning(f"Skipping non-serializable service data: {service_key}={service_count}")
                
                clean_stats[str(user_id)] = {
                    'first_seen': str(user_data.get('first_seen', '')),
                    'last_seen': str(user_data.get('last_seen', '')),
                    'username': str(user_data.get('username', '')) if user_data.get('username') else None,
                    'first_name': str(user_data.get('first_name', '')) if user_data.get('first_name') else None,
                    'total_messages': int(user_data.get('total_messages', 0)),
                    'services_used': services_used
                }
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(clean_stats, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving stats file: {e}")
            logger.error(f"Stats content that failed: {self.stats}")

    def track_user(self, user_id: int, username: str = None, first_name: str = None, 
                   message_type: str = "message", service_name: str = None):
        """Track user activity in background"""
        user_id_str = str(user_id)
        now = datetime.now().isoformat()
        
        if user_id_str not in self.stats:
            self.stats[user_id_str] = {
                'first_seen': now,
                'username': username,
                'first_name': first_name,
                'total_messages': 0,
                'services_used': {},
                'last_seen': now
            }
        
        user = self.stats[user_id_str]
        user['last_seen'] = now
        user['total_messages'] += 1
        
        # Update user info if provided - ensure they're strings or None
        if username:
            user['username'] = str(username)
        if first_name:
            user['first_name'] = str(first_name)
            
        # Track service usage - ensure service_name is a string
        if service_name:
            service_name = str(service_name)  # Convert to string to be safe
            if 'services_used' not in user:
                user['services_used'] = {}
            if service_name not in user['services_used']:
                user['services_used'][service_name] = 0
            user['services_used'][service_name] += 1
        
        self._save_stats()
import os
import json
from dataclasses import dataclass
from typing import Optional

@dataclass
class ServerConfig:
    host: str = '0.0.0.0'
    port: int = 12345
    video_port: int = 12346
    ui_video_port: int = 12347
    ui_control_port: int = 12348
    max_clients: int = 10
    
@dataclass
class ClientConfig:
    server_host: str = '127.0.0.1'
    server_port: int = 12345
    video_port: int = 12346
    client_name: str = 'SourceAgent'
    video_quality: int = 50
    video_width: int = 800
    fps: int = 30
    
@dataclass
class SecurityConfig:
    use_tls: bool = True
    certs_dir: str = '../certs'
    ca_cert: str = 'ca.crt'
    server_cert: str = 'server.crt'
    server_key: str = 'server.key'
    client_cert: str = 'client.crt'
    client_key: str = 'client.key'
    
@dataclass
class UIConfig:
    host: str = '0.0.0.0'
    port: int = 8501
    server_host: str = '127.0.0.1'
    server_port: int = 12345
    ui_control_port: int = 12348
    ui_video_port: int = 12347
    auto_start_server: bool = True
    frame_update_rate: float = 0.033  # ~30 FPS

@dataclass
class AppConfig:
    server: ServerConfig
    client: ClientConfig
    security: SecurityConfig
    ui: UIConfig
    debug: bool = False
    
    @classmethod
    def load(cls, config_file: Optional[str] = None) -> 'AppConfig':
        """Load configuration from file and environment variables."""
        config_data = {}
        
        # Load from file if provided
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_data = json.load(f)
        
        # Override with environment variables
        env_overrides = {
            'debug': os.getenv('NETKVM_DEBUG', 'false').lower() == 'true',
            'server': {
                'host': os.getenv('NETKVM_SERVER_HOST', config_data.get('server', {}).get('host', '0.0.0.0')),
                'port': int(os.getenv('NETKVM_SERVER_PORT', config_data.get('server', {}).get('port', 12345))),
                'video_port': int(os.getenv('NETKVM_VIDEO_PORT', config_data.get('server', {}).get('video_port', 12346))),
            },
            'client': {
                'server_host': os.getenv('NETKVM_CLIENT_SERVER_HOST', config_data.get('client', {}).get('server_host', '127.0.0.1')),
                'server_port': int(os.getenv('NETKVM_CLIENT_SERVER_PORT', config_data.get('client', {}).get('server_port', 12345))),
                'client_name': os.getenv('NETKVM_CLIENT_NAME', config_data.get('client', {}).get('client_name', 'SourceAgent')),
            },
            'security': {
                'use_tls': os.getenv('NETKVM_USE_TLS', 'true').lower() == 'true',
                'certs_dir': os.getenv('NETKVM_CERTS_DIR', config_data.get('security', {}).get('certs_dir', '../certs')),
            }
        }
        
        # Deep merge configuration data
        def deep_merge(base, override):
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
        
        deep_merge(config_data, env_overrides)
        
        # Create config objects
        server_config = ServerConfig(**config_data.get('server', {}))
        client_config = ClientConfig(**config_data.get('client', {}))
        security_config = SecurityConfig(**config_data.get('security', {}))
        ui_config = UIConfig(**config_data.get('ui', {}))
        
        return cls(
            server=server_config,
            client=client_config,
            security=security_config,
            ui=ui_config,
            debug=config_data.get('debug', False)
        )
    
    def save(self, config_file: str):
        """Save configuration to file."""
        config_data = {
            'server': self.server.__dict__,
            'client': self.client.__dict__,
            'security': self.security.__dict__,
            'ui': self.ui.__dict__,
            'debug': self.debug
        }
        
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
    
    def get_certs_dir(self, base_path: str = None) -> str:
        """Get absolute path to certificates directory."""
        if base_path is None:
            # Get path relative to the current file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_path = os.path.join(current_dir, '..', '..', '..')
        
        return os.path.abspath(os.path.join(base_path, self.security.certs_dir))

# Global configuration instance - load from default config file if it exists
_default_config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
config = AppConfig.load(_default_config_path if os.path.exists(_default_config_path) else None) 
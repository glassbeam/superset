import json
import logging
import sys
from pathlib import Path


def load_credentials(credential_path, credential_type="json"):
   
    try:
        cred_file = Path(credential_path)
        
        if not cred_file.exists():
            raise FileNotFoundError(
                f"Credential file not found at: {credential_path}\n"
                f"Please ensure the credential file exists and is accessible."
            )
        
        if not cred_file.is_file():
            raise FileNotFoundError(
                f"Credential path is not a file: {credential_path}"
            )
        
        # Check file permissions (should not be world-readable for security)
        file_stat = cred_file.stat()
        if file_stat.st_mode & 0o077:
            logging.warning(
                f"Warning: Credential file {credential_path} may have overly permissive permissions. "
                f"Consider restricting to 0600 (owner read/write only)."
            )
        
        with open(cred_file, 'r') as f:
            if credential_type == "json":
                credentials = json.load(f)
            elif credential_type == "env":
                # Parse KEY=VALUE format
                credentials = {}
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            credentials[key.strip()] = value.strip()
            else:
                raise ValueError(f"Unknown credential type: {credential_type}")
        
        logging.info(f"Successfully loaded credentials from {credential_path}")
        return credentials
    
    except FileNotFoundError as e:
        logging.error(str(e))
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in credential file {credential_path}: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Error loading credentials from {credential_path}: {str(e)}")
        raise


def get_vertica_config(config, credential_path=None):

    cred_path = credential_path or config["vertica"].get("credentials_path")
    
    try:
        creds = load_credentials(cred_path, credential_type="json")
    except Exception as e:
        logging.error(f"Failed to load Vertica credentials: {str(e)}")
        raise
    
    vertica_config = {
        "host": creds.get("host") or config["vertica"].get("ums_host"),
        "port": creds.get("port") or config["vertica"].get("port", 5433),
        "user": creds.get("username"),
        "password": creds.get("password"),
        "database": creds.get("database") or config["vertica"].get("database"),
        "autocommit": True,
        "tlsmode": "disable"
    }
    
    # Validate required fields
    required_fields = ["user", "password", "host", "database"]
    missing_fields = [f for f in required_fields if not vertica_config.get(f)]
    
    if missing_fields:
        raise ValueError(
            f"Missing required Vertica credentials: {', '.join(missing_fields)} "
            f"in {cred_path}"
        )
    
    return vertica_config


def get_superset_credentials(config, credential_path=None):
    cred_path = credential_path or config["superset"].get("credentials_path")
    
    try:
        creds = load_credentials(cred_path, credential_type="json")
    except Exception as e:
        logging.error(f"Failed to load Superset credentials: {str(e)}")
        raise
    
    superset_creds = {
        "username": creds.get("username"),
        "password": creds.get("password")
    }
    
    # Validate required fields
    if not superset_creds["username"] or not superset_creds["password"]:
        raise ValueError(
            f"Missing username or password in Superset credentials at {cred_path}"
        )
    
    return superset_creds
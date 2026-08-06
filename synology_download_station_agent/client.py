import os
import sys
import requests
from typing import Dict, Any, Optional, List
from urllib.parse import unquote
from dotenv import load_dotenv

# Load local .env if present
load_dotenv()


class SynologyClientError(Exception):
    """Base exception for Synology API errors."""
    pass


class SynologyAuthError(SynologyClientError):
    """Raised when authentication fails."""
    pass


class SynologyTaskError(SynologyClientError):
    """Raised when Download Station task operations fail."""
    pass


def clean_magnet_uri(uri: str) -> str:
    """
    Sanitizes and cleans magnet URIs before sending to Synology API.
    Resolves pre-percent-encoded characters (e.g. %3A, %2F) so that
    HTTP POST form-encoding does not double-encode % into %25, which
    causes Synology Download Station tracker resolution to fail.
    """
    if not uri:
        return uri
    clean_str = uri.strip()
    if clean_str.startswith("magnet:?"):
        # Unquote once to prevent double url-encoding on trackers and display names
        decoded = unquote(clean_str)
        if decoded.startswith("magnet:?"):
            return decoded
    return clean_str


class SynologyClient:
    """DSM 7 Optimized Client for interacting with Synology NAS Download Station API over LAN."""

    def __init__(
        self,
        ip: Optional[str] = None,
        port: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_https: Optional[bool] = None,
        verify_ssl: Optional[bool] = None,
        timeout: int = 15,
    ):
        self.ip = ip or os.getenv("SYNO_LOCAL_IP", "192.168.1.100")
        self.port = port or os.getenv("SYNO_LOCAL_PORT", "5000")
        self.username = username or os.getenv("SYNO_USER", "hermes_bot")
        self.password = password or os.getenv("SYNO_PASS", "")

        env_https = os.getenv("SYNO_USE_HTTPS", "false").lower() in ("true", "1", "yes")
        self.use_https = use_https if use_https is not None else env_https

        env_verify = os.getenv("SYNO_VERIFY_SSL", "true").lower() in ("true", "1", "yes")
        self.verify_ssl = verify_ssl if verify_ssl is not None else env_verify

        self.timeout = timeout
        self.session = requests.Session()
        self.sid: Optional[str] = None
        self.task_api_version: Optional[str] = os.getenv("SYNO_TASK_API_VERSION", None)
        self.task_api_path: str = "entry.cgi"

        self.protocol = "https" if self.use_https else "http"
        self.base_url = f"{self.protocol}://{self.ip}:{self.port}/webapi/{self.task_api_path}"

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()

    def get_api_info(self, api_name: str = "SYNO.DownloadStation.Task") -> Dict[str, Any]:
        """Query DSM 7 API Info for supported API versions and entry path."""
        info_url = f"{self.protocol}://{self.ip}:{self.port}/webapi/query.cgi"
        params = {
            "api": "SYNO.API.Info",
            "version": "1",
            "method": "query",
            "query": api_name,
        }
        try:
            resp = self.session.get(
                info_url,
                params=params,
                verify=self.verify_ssl,
                timeout=self.timeout,
            ).json()
            if resp.get("success"):
                return resp.get("data", {}).get(api_name, {})
        except Exception:
            pass
        return {}

    def login(self) -> str:
        """Authenticate with DSM 7 and retrieve session ID (sid). Try DSM 7 API versions 7 -> 6 -> 3 -> 1."""
        auth_versions = ["7", "6", "3", "1"]
        last_error = None

        for ver in auth_versions:
            auth_params = {
                "api": "SYNO.API.Auth",
                "version": ver,
                "method": "login",
                "account": self.username,
                "passwd": self.password,
                "session": "DownloadStation",
                "format": "sid",
            }
            try:
                resp = self.session.get(
                    f"{self.protocol}://{self.ip}:{self.port}/webapi/entry.cgi",
                    params=auth_params,
                    verify=self.verify_ssl,
                    timeout=self.timeout,
                ).json()
            except Exception as e:
                raise SynologyClientError(f"Network error during NAS authentication: {e}")

            if resp.get("success"):
                self.sid = resp["data"]["sid"]
                return self.sid

            error_code = resp.get("error", {}).get("code")
            last_error = resp
            if error_code in (102, 104):
                continue
            else:
                break

        error_code = last_error.get("error", {}).get("code", "unknown") if last_error else "unknown"
        raise SynologyAuthError(
            f"Failed to authenticate with DSM 7 NAS (Error code: {error_code}). Response: {last_error}"
        )

    def _call_task_api(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        http_method: str = "GET",
    ) -> Dict[str, Any]:
        """Executes a DSM 7 SYNO.DownloadStation.Task API call with automatic version resolution."""
        if not self.sid:
            self.login()

        # Query DSM 7 API Info dynamically if version is not cached
        if not self.task_api_version:
            api_info = self.get_api_info("SYNO.DownloadStation.Task")
            if api_info:
                max_ver = str(api_info.get("maxVersion", 3))
                path = api_info.get("path", "entry.cgi")
                self.task_api_version = max_ver
                self.task_api_path = path
                self.base_url = f"{self.protocol}://{self.ip}:{self.port}/webapi/{self.task_api_path}"

        candidate_versions = [self.task_api_version] if self.task_api_version else ["3", "2", "1"]
        last_resp = None

        for ver in candidate_versions:
            req_params = {
                "api": "SYNO.DownloadStation.Task",
                "version": ver,
                "method": method,
                "_sid": self.sid,
            }
            if params:
                req_params.update(params)

            req_data = None
            if data:
                req_data = {
                    "api": "SYNO.DownloadStation.Task",
                    "version": ver,
                    "method": method,
                    "_sid": self.sid,
                }
                req_data.update(data)

            try:
                if http_method.upper() == "POST":
                    resp = self.session.post(
                        self.base_url,
                        data=req_data,
                        params=req_params if not req_data else None,
                        verify=self.verify_ssl,
                        timeout=self.timeout,
                    ).json()
                else:
                    resp = self.session.get(
                        self.base_url,
                        params=req_params,
                        verify=self.verify_ssl,
                        timeout=self.timeout,
                    ).json()
            except Exception as e:
                raise SynologyTaskError(f"Network error during Download Station task '{method}': {e}")

            if resp.get("success"):
                self.task_api_version = ver
                return resp

            error_code = resp.get("error", {}).get("code")
            last_resp = resp

            # Code 102/104 = API version/parameter error -> try fallback version
            if error_code in (102, 104):
                continue
            else:
                break

        err_code = last_resp.get("error", {}).get("code") if last_resp else None
        hint = ""
        if err_code in (102, 105):
            hint = (
                f"\n[DSM 7 Troubleshooting Hint]: Verify that user '{self.username}' has 'Download Station' "
                f"application permission enabled in DSM 7 Control Panel > User & Group > Edit User > Application Permissions."
            )
        elif err_code == 403:
            hint = (
                f"\n[Error 403 Hint]: Destination folder does not exist or permission denied. "
                f"Check the exact Shared Folder name in DSM > File Station (case-sensitive, e.g. 'downloads' vs 'Downloads')."
            )
        elif err_code == 406:
            hint = (
                f"\n[Error 406 Hint]: Destination folder is required. Either set a default download location in DSM Download Station Settings "
                f"(DSM > Download Station > Settings > Location), or set SYNO_DEFAULT_DESTINATION in .env (e.g. SYNO_DEFAULT_DESTINATION=downloads)."
            )

        raise SynologyTaskError(f"Failed task operation '{method}': {last_resp}{hint}")

    def add_magnet(self, magnet_uri: str, destination: Optional[str] = None) -> Dict[str, Any]:
        """Add a magnet link or download URI to Download Station on DSM 7."""
        clean_uri = clean_magnet_uri(magnet_uri)
        data = {"uri": clean_uri}
        dest = destination or os.getenv("SYNO_DEFAULT_DESTINATION", None)
        if dest:
            data["destination"] = dest

        try:
            return self._call_task_api("create", data=data, http_method="POST")
        except SynologyTaskError as e:
            # If invalid destination caused Error 403, retry without destination so DSM uses its default folder
            if dest and ("403" in str(e) or "'code': 403" in str(e)):
                data_no_dest = {"uri": clean_uri}
                return self._call_task_api("create", data=data_no_dest, http_method="POST")
            raise e

    def list_tasks(
        self,
        additional: Optional[List[str]] = None,
        task_type: Optional[str] = "all",
    ) -> Dict[str, Any]:
        """List tasks in Download Station on DSM 7. Default task_type='all' includes completed/finished tasks."""
        params = {}
        if task_type:
            params["type"] = task_type
        if additional:
            params["additional"] = ",".join(additional)

        try:
            return self._call_task_api("list", params=params, http_method="GET")
        except SynologyTaskError:
            if additional or task_type:
                return self._call_task_api("list", params={}, http_method="GET")
            raise

    def delete_task(self, task_ids: List[str], force_complete: bool = False) -> Dict[str, Any]:
        """Delete one or more download tasks by ID on DSM 7."""
        params = {
            "id": ",".join(task_ids),
            "force_complete": "true" if force_complete else "false",
        }
        return self._call_task_api("delete", params=params, http_method="GET")

    def logout(self) -> bool:
        """Logout and invalidate session ID."""
        if not self.sid:
            return True

        params = {
            "api": "SYNO.API.Auth",
            "version": "1",
            "method": "logout",
            "_sid": self.sid,
        }
        try:
            resp = self.session.get(
                f"{self.protocol}://{self.ip}:{self.port}/webapi/entry.cgi",
                params=params,
                verify=self.verify_ssl,
                timeout=self.timeout,
            ).json()
            self.sid = None
            return resp.get("success", False)
        except Exception:
            self.sid = None
            return False

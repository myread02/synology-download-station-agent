import unittest
from unittest.mock import patch, MagicMock
from synology_download_station_agent.client import SynologyClient, SynologyAuthError, SynologyTaskError, SynologyClientError, clean_magnet_uri
from synology_download_station_agent.poll import check_and_notify_finished_tasks, send_telegram_notification


class TestSynologyClient(unittest.TestCase):

    def setUp(self):
        self.client = SynologyClient(
            ip="192.168.1.100",
            port="5000",
            username="testuser",
            password="testpass",
            use_https=False,
            verify_ssl=True,
        )

    def test_clean_magnet_uri(self):
        # Verify pre-encoded tracker URLs are unquoted cleanly
        encoded_magnet = "magnet:?xt=urn:btih:12345&tr=udp%3A%2F%2Ftracker.open.org%3A1337"
        expected = "magnet:?xt=urn:btih:12345&tr=udp://tracker.open.org:1337"
        self.assertEqual(clean_magnet_uri(encoded_magnet), expected)

    @patch("requests.Session.get")
    def test_login_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "data": {"sid": "mocked_session_id_12345"}
        }
        mock_get.return_value = mock_resp

        sid = self.client.login()
        self.assertEqual(sid, "mocked_session_id_12345")
        self.assertEqual(self.client.sid, "mocked_session_id_12345")

    @patch("requests.Session.get")
    def test_login_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": False,
            "error": {"code": 400}
        }
        mock_get.return_value = mock_resp

        with self.assertRaises(SynologyAuthError):
            self.client.login()

    @patch("requests.Session.post")
    @patch("requests.Session.get")
    def test_add_magnet_success(self, mock_get, mock_post):
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = {
            "success": True,
            "data": {"sid": "mocked_sid"}
        }
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_post_resp

        magnet = "magnet:?xt=urn:btih:test"
        res = self.client.add_magnet(magnet)
        self.assertTrue(res.get("success"))

    @patch("requests.Session.get")
    def test_list_tasks_success(self, mock_get):
        self.client.sid = "existing_sid"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                "tasks": [
                    {"id": "db_1", "title": "ubuntu.iso", "status": "finished"},
                    {"id": "db_2", "title": "debian.iso", "status": "downloading"},
                ]
            }
        }
        mock_get.return_value = mock_resp

        res = self.client.list_tasks()
        tasks = res["data"]["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["title"], "ubuntu.iso")

    @patch("requests.Session.get")
    def test_list_tasks_fallback_on_error_102(self, mock_get):
        """Verify that API version 1 is tried if version 3 returns error 102."""
        self.client.sid = "existing_sid"
        self.client.task_api_version = None

        mock_resp_102 = MagicMock()
        mock_resp_102.json.return_value = {"success": False, "error": {"code": 102}}

        mock_resp_success = MagicMock()
        mock_resp_success.json.return_value = {
            "success": True,
            "data": {"tasks": [{"id": "t1", "title": "test", "status": "downloading"}]}
        }

        mock_get.side_effect = [mock_resp_102, mock_resp_success]

        res = self.client.list_tasks()
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["tasks"][0]["id"], "t1")

    @patch("requests.Session.get")
    def test_delete_task(self, mock_get):
        self.client.sid = "existing_sid"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True}
        mock_get.return_value = mock_resp

        res = self.client.delete_task(["db_1"])
        self.assertTrue(res["success"])

    @patch("requests.post")
    def test_send_telegram_notification(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        success = send_telegram_notification("token123", "chat123", "Test Alert")
        self.assertTrue(success)

    @patch("requests.post")
    @patch.object(SynologyClient, "list_tasks")
    def test_check_and_notify_finished_tasks(self, mock_list_tasks, mock_post):
        mock_list_tasks.return_value = {
            "success": True,
            "data": {
                "tasks": [
                    {"id": "task_1", "title": "ArchLinux.iso", "status": "finished"},
                ]
            }
        }
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_post_resp

        finished = check_and_notify_finished_tasks(
            self.client,
            telegram_bot_token="token_xyz",
            telegram_chat_id="chat_xyz"
        )
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["id"], "task_1")


if __name__ == "__main__":
    unittest.main()

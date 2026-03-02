import sys
from unittest.mock import MagicMock, patch
import unittest
from src.api.notification import AlertManager
from config.settings import Settings

class TestAlertManager(unittest.TestCase):
    def setUp(self):
        # Mock settings
        self.original_feishu = Settings.FEISHU_WEBHOOK
        self.original_dingtalk = Settings.DINGTALK_WEBHOOK
        Settings.FEISHU_WEBHOOK = "https://test.feishu.cn"
        Settings.DINGTALK_WEBHOOK = "https://test.dingtalk.com"
        Settings.DINGTALK_ALERT_ENABLE = True
        Settings.DINGTALK_SECRET = ""

    def tearDown(self):
        Settings.FEISHU_WEBHOOK = self.original_feishu
        Settings.DINGTALK_WEBHOOK = self.original_dingtalk

    @patch('src.api.notification.requests.post')
    def test_send_feishu_success(self, mock_post):
        """Test successful Feishu alert"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        AlertManager.send_feishu("test message")
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], Settings.FEISHU_WEBHOOK)
        self.assertIn("content", kwargs['data'])

    @patch('src.api.notification.requests.post')
    def test_send_dingtalk_success(self, mock_post):
        """Test successful DingTalk alert"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        AlertManager.send_dingtalk("test message")
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        # The URL might be different if secret is used, but here secret is empty
        self.assertTrue(args[0].startswith(Settings.DINGTALK_WEBHOOK))
        self.assertIn("text", kwargs['json'])

    @patch('src.api.notification.AlertManager.send_feishu')
    @patch('src.api.notification.AlertManager.send_dingtalk')
    def test_send_alert_routing(self, mock_send_dingtalk, mock_send_feishu):
        """Test alert routing based on market"""
        
        # Test HK -> Feishu
        AlertManager.send_alert("Title", "Content", market="HK")
        mock_send_feishu.assert_called_once()
        mock_send_dingtalk.assert_not_called()
        
        mock_send_feishu.reset_mock()
        mock_send_dingtalk.reset_mock()
        
        # Test US -> DingTalk
        AlertManager.send_alert("Title", "Content", market="US")
        mock_send_feishu.assert_not_called()
        mock_send_dingtalk.assert_called_once()

    def test_missing_webhook(self):
        """Test behavior when webhook is missing"""
        Settings.FEISHU_WEBHOOK = ""
        with patch('src.api.notification.requests.post') as mock_post:
            AlertManager.send_feishu("test")
            mock_post.assert_not_called()

if __name__ == '__main__':
    unittest.main()

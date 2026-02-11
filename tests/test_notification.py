import sys
from unittest.mock import MagicMock, patch

# Mock longport modules BEFORE importing src.api
# This is needed because src.api imports src.api.trade which imports longport
sys.modules["longport"] = MagicMock()
sys.modules["longport.openapi"] = MagicMock()

import unittest
from src.api.notification import AlertManager
from src.config import Config

class TestAlertManager(unittest.TestCase):
    def setUp(self):
        Config.FEISHU_WEBHOOK = "https://test.feishu.cn"
        Config.DINGTALK_WEBHOOK = "https://test.dingtalk.com"

    @patch('src.api.notification.requests.post')
    def test_send_feishu_success(self, mock_post):
        """Test successful Feishu alert"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        AlertManager.send_feishu("test message")
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], Config.FEISHU_WEBHOOK)
        self.assertIn("content", kwargs['json'])

    @patch('src.api.notification.requests.post')
    def test_send_dingtalk_success(self, mock_post):
        """Test successful DingTalk alert"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        AlertManager.send_dingtalk("test message")
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], Config.DINGTALK_WEBHOOK)
        self.assertIn("text", kwargs['json'])

    @patch('src.api.notification.requests.post')
    def test_send_alert_all_channels(self, mock_post):
        """Test sending to all channels"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        AlertManager.send_alert("Title", "Content")
        
        # Should call post twice (once for Feishu, once for DingTalk)
        self.assertEqual(mock_post.call_count, 2)

    def test_missing_webhook(self):
        """Test behavior when webhook is missing"""
        Config.FEISHU_WEBHOOK = ""
        with patch('src.api.notification.requests.post') as mock_post:
            AlertManager.send_feishu("test")
            mock_post.assert_not_called()

if __name__ == '__main__':
    unittest.main()

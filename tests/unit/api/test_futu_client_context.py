import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from src.api.futu.client import FutuClient


class TestFutuClientContext(unittest.TestCase):
    def setUp(self):
        self.client = FutuClient()
        self.client._quote_ctx = None

    def tearDown(self):
        self.client.close()

    @patch("src.api.futu.client.OpenQuoteContext")
    def test_concurrent_initialization_creates_one_context(self, mock_context_class):
        context = MagicMock()
        context.status = True

        def create_context(*args, **kwargs):
            time.sleep(0.02)
            return context

        mock_context_class.side_effect = create_context

        with ThreadPoolExecutor(max_workers=8) as executor:
            contexts = list(executor.map(lambda _: self.client.get_quote_context(), range(16)))

        self.assertTrue(all(item is context for item in contexts))
        mock_context_class.assert_called_once()
        context.start.assert_called_once()

    def test_close_is_idempotent_even_when_context_close_fails(self):
        context = MagicMock()
        context.close.side_effect = RuntimeError("close failed")
        self.client._quote_ctx = context

        self.client.close()
        self.client.close()

        context.close.assert_called_once()
        self.assertIsNone(self.client._quote_ctx)


if __name__ == "__main__":
    unittest.main()

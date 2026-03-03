import unittest
import os
import shutil
import logging
from src.utils.logger import setup_logger

class TestLogger(unittest.TestCase):
    def setUp(self):
        self.test_log_file = "test_logs/test.log"
        # Ensure directory is clean
        if os.path.exists("test_logs"):
            # Try to remove, if fails (locked), ignore for setup but might fail later
            try:
                shutil.rmtree("test_logs")
            except:
                pass

    def tearDown(self):
        # Close all handlers associated with the logger
        logger = logging.getLogger("test_logger")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
            
        if os.path.exists("test_logs"):
            try:
                shutil.rmtree("test_logs")
            except PermissionError:
                # On Windows, sometimes file release is delayed
                pass

    def test_logger_creation(self):
        """Test if logger is created with correct name and level"""
        logger = setup_logger("test_logger", self.test_log_file)
        self.assertEqual(logger.name, "test_logger")
        self.assertEqual(logger.level, logging.INFO)
        self.assertTrue(os.path.exists(self.test_log_file))

    def test_logger_singleton_behavior(self):
        """Test if calling setup_logger twice returns same logger without duplicate handlers"""
        logger1 = setup_logger("test_logger", self.test_log_file)
        logger2 = setup_logger("test_logger", self.test_log_file)
        
        self.assertEqual(logger1, logger2)
        # Should have 2 handlers (console + file)
        self.assertEqual(len(logger1.handlers), 2)

    def test_logging_output(self):
        """Test if logs are written to file"""
        logger = setup_logger("test_logger", self.test_log_file)
        logger.info("Test log message")
        
        # Close handlers to flush and release file
        for handler in logger.handlers:
            handler.close()

        with open(self.test_log_file, 'r') as f:
            content = f.read()
            self.assertIn("Test log message", content)

if __name__ == '__main__':
    unittest.main()

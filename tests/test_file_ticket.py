import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from core.file_ticket_service import FileTicketService


class FileTicketTest(unittest.TestCase):
    def test_ticket_is_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.txt"
            path.write_text("demo", encoding="utf-8")
            service = FileTicketService(ttl_seconds=60)
            ticket, _ = service.create("student", path)
            self.assertEqual(service.resolve(ticket, "student"), path)
            self.assertIsNone(service.resolve(ticket, "student"))

    def test_expired_ticket_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.txt"
            path.write_text("demo", encoding="utf-8")
            service = FileTicketService(ttl_seconds=10)
            ticket, _ = service.create("student", path)
            record = service._tickets[ticket]
            record.expires_at = record.expires_at - timedelta(seconds=30)
            self.assertIsNone(service.resolve(ticket, "student"))


if __name__ == "__main__":
    unittest.main()
import os
import unittest

os.environ.setdefault("WHO_COULD_SECRET", "engine-tests-only-secret-at-least-32-characters")
os.environ.setdefault("DATABASE_URL", "mariadb+pymysql://user:password@localhost:3306/test")

from sqlalchemy import URL

from app.config import Settings
from app.database_engine import database_connect_args


def configured(*, ca=None):
    return Settings(
        environment="production",
        database_url=URL.create("mariadb+pymysql", database="test"),
        secret="x" * 32,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        pool_pre_ping=True,
        database_ssl_ca=ca,
    )


class ConnectArgsTest(unittest.TestCase):
    def test_mariadb_without_ca(self):
        self.assertEqual(database_connect_args(configured(), "mariadb"), {})

    def test_mariadb_uses_ca(self):
        self.assertEqual(
            database_connect_args(configured(ca="/secure/maria-ca.pem"), "mariadb"),
            {"ssl": {"ca": "/secure/maria-ca.pem"}},
        )

    def test_other_engines_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Only MariaDB is supported"):
            database_connect_args(configured(), "postgresql")


if __name__ == "__main__":
    unittest.main()

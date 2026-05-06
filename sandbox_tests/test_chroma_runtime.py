import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeCollection:
    def __init__(self, count=3):
        self._count = count

    def count(self):
        return self._count


class FakePersistentClient:
    calls = []

    def __init__(self, path):
        self.path = path
        self.collections = {"wintrip_knowledge": FakeCollection(7)}
        self.calls.append(("persistent", path))

    def get_or_create_collection(self, **kwargs):
        return self.collections.setdefault(kwargs["name"], FakeCollection())

    def get_collection(self, name):
        if name not in self.collections:
            raise RuntimeError("missing")
        return self.collections[name]

    def heartbeat(self):
        return 123


class FakeHttpClient:
    calls = []

    def __init__(self, host, port, ssl):
        self.host = host
        self.port = port
        self.ssl = ssl
        self.collections = {"wintrip_training_11d": FakeCollection(11)}
        self.calls.append(("http", host, port, ssl))

    def get_or_create_collection(self, **kwargs):
        return self.collections.setdefault(kwargs["name"], FakeCollection())

    def get_collection(self, name):
        if name not in self.collections:
            raise RuntimeError("missing")
        return self.collections[name]

    def heartbeat(self):
        return 456


class TestChromaRuntime(unittest.TestCase):
    def setUp(self):
        self.old_env = {
            "WINTRIP_CHROMA_HTTP_URL": os.environ.get("WINTRIP_CHROMA_HTTP_URL"),
            "WINTRIP_DB_PATH": os.environ.get("WINTRIP_DB_PATH"),
        }
        self.old_chromadb = sys.modules.get("chromadb")
        fake = types.ModuleType("chromadb")
        fake.PersistentClient = FakePersistentClient
        fake.HttpClient = FakeHttpClient
        sys.modules["chromadb"] = fake
        FakePersistentClient.calls.clear()
        FakeHttpClient.calls.clear()

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self.old_chromadb is None:
            sys.modules.pop("chromadb", None)
        else:
            sys.modules["chromadb"] = self.old_chromadb

    def test_persistent_client_is_default(self):
        from controller.chroma_runtime import chroma_client, chroma_runtime_status

        with tempfile.TemporaryDirectory(prefix="chroma-runtime-") as tmp:
            os.environ.pop("WINTRIP_CHROMA_HTTP_URL", None)
            os.environ["WINTRIP_DB_PATH"] = tmp

            client = chroma_client()
            self.assertEqual(client.path, tmp)
            self.assertEqual(FakePersistentClient.calls[0], ("persistent", tmp))

            status = chroma_runtime_status(["wintrip_knowledge"])
            self.assertEqual(status["mode"], "persistent")
            self.assertEqual(status["collections"]["wintrip_knowledge"]["count"], 7)

    def test_http_client_is_selected_from_env(self):
        from controller.chroma_runtime import chroma_client, chroma_runtime_status

        os.environ["WINTRIP_CHROMA_HTTP_URL"] = "http://chroma:8000"

        client = chroma_client()
        self.assertEqual((client.host, client.port, client.ssl), ("chroma", 8000, False))
        self.assertEqual(FakeHttpClient.calls[0], ("http", "chroma", 8000, False))

        status = chroma_runtime_status(["wintrip_training_11d"])
        self.assertEqual(status["mode"], "http")
        self.assertEqual(status["remote_url"], "http://chroma:8000")
        self.assertEqual(status["collections"]["wintrip_training_11d"]["count"], 11)

    def test_remote_url_status_redacts_credentials(self):
        from controller.chroma_runtime import chroma_runtime_config

        os.environ["WINTRIP_CHROMA_HTTP_URL"] = "https://user:secret@example.test:8443/private?token=nope"
        config = chroma_runtime_config()
        self.assertEqual(config["remote_url"], "https://example.test:8443/private")
        self.assertNotIn("secret", str(config))
        self.assertNotIn("token=nope", str(config))


if __name__ == "__main__":
    unittest.main()

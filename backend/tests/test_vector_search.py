import unittest
import numpy as np
from app.db.vector_search import _embedding_to_pgvector_literal, search_similar_faces


class TestVectorSearch(unittest.TestCase):

    def test_embedding_to_pgvector_literal(self):
        emb = np.array([0.25, 0.75], dtype=np.float32)
        literal = _embedding_to_pgvector_literal(emb)
        self.assertTrue(literal.startswith("["))
        self.assertTrue(literal.endswith("]"))
        self.assertIn("0.25", literal)
        self.assertIn("0.75", literal)

    def test_search_similar_faces_sqlite_fallback(self):
        class FakeCursor:
            def execute(self, sql, params=None):
                pass
            def fetchall(self):
                return []

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        emb = np.zeros(512, dtype=np.float32)
        results = search_similar_faces(FakeConn(), emb)
        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()

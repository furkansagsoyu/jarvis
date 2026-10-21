import unittest
from main import topla

class TestTopla(unittest.TestCase):
    def test_pozitif(self):
        self.assertEqual(topla(2, 3), 5)

    def test_negatif(self):
        self.assertEqual(topla(-1, 1), 0)

    def test_sifir(self):
        self.assertEqual(topla(0, 0), 0)

if __name__ == "__main__":
    unittest.main()

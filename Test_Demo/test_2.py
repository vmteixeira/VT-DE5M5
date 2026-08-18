import unittest
from calculator import Calculator

class TestOperatios(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator(a=8, b=2)

    def test_get_sum(self):
        self.assertEqual(self.calc.get_sum(), 10)

    def test_get_difference(self):
        self.assertEqual(self.calc.get_difference(), 6)

    def test_get_product(self):
        self.assertEqual(self.calc.get_product(), 16)

    def test_get_quotient(self):
        self.assertEqual(self.calc.get_quotient(), 4)

    def test_get_quotient_zero_denominator(self):
        calc = Calculator(a=3, b=0)
        with self.assertRaises(ValueError):
            calc.get_quotient()

# Research pyTest



if __name__ == '__main__':
    unittest.main()
class Calculator:
    def __init__(self, a, b):
        self.a = a
        self.b = b

    def get_quotient(self):
        if self.b != 0:
            return self.a / self.b
        else:
            raise ValueError("Denominator cannot be zero.")


if __name__ == "__main__":
    my_calc = Calculator(145, 12)
    print(my_calc.get_quotient())

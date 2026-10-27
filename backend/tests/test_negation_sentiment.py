import unittest
from model_service import SentimentModel

class NegationSentimentTests(unittest.TestCase):
    def test_not_bad_is_positive(self):
        self.assertEqual(SentimentModel._negation_sentiment("You are not bad"), "positive")

    def test_not_good_is_negative(self):
        self.assertEqual(SentimentModel._negation_sentiment("This product is not good"), "negative")

    def test_not_terrible_is_positive(self):
        self.assertEqual(SentimentModel._negation_sentiment("The service is not terrible at all"), "positive")

    def test_not_great_is_negative(self):
        self.assertEqual(SentimentModel._negation_sentiment("The experience was not great"), "negative")

    def test_not_only_is_not_flipped(self):
        self.assertIsNone(SentimentModel._negation_sentiment("It is not only good, it is excellent"))

    def test_simple_good_is_positive(self):
        self.assertEqual(SentimentModel._negation_sentiment("This is good"), "positive")

    def test_simple_bad_is_negative(self):
        self.assertEqual(SentimentModel._negation_sentiment("This is bad"), "negative")

    def test_unrelated_text_uses_model(self):
        self.assertIsNone(SentimentModel._negation_sentiment("The package arrived yesterday"))

if __name__ == "__main__":
    unittest.main()

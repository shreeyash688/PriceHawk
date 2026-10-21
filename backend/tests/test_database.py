from database import db
from exceptions import DuplicateProductError, ProductNotFoundError
from tests.helpers import BOOK_URL, DatabaseTestCase


class DatabaseTests(DatabaseTestCase):
    def test_create_and_read(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0)
        row = db.get_product(product_id)
        self.assertEqual(row["title"], "Book A")
        self.assertEqual(row["tracking_active"], 1)
        self.assertEqual(len(db.get_all_products()), 1)

    def test_update(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0)
        db.update_target_price(product_id, 12.0)
        db.set_tracking_active(product_id, False)
        row = db.get_product(product_id)
        self.assertEqual(row["target_price"], 12.0)
        self.assertEqual(row["tracking_active"], 0)

    def test_delete_also_removes_history(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0)
        db.add_price_history(product_id, 20.0)
        db.delete_product(product_id)
        with self.assertRaises(ProductNotFoundError):
            db.get_product(product_id)
        self.assertEqual(list(db.iter_price_history()), [])

    def test_duplicate_url_rejected(self):
        db.add_product("Book A", BOOK_URL, 20.0, 15.0)
        with self.assertRaises(DuplicateProductError):
            db.add_product("Book A again", BOOK_URL, 20.0, 15.0)

    def test_missing_product(self):
        with self.assertRaises(ProductNotFoundError):
            db.get_product(999)
        with self.assertRaises(ProductNotFoundError):
            db.delete_product(999)

    def test_history_generator(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0)
        for price in (20.0, 19.0, 18.0):
            db.add_price_history(product_id, price)
        prices = [row["price"] for row in db.iter_price_history(product_id, batch_size=2)]
        self.assertEqual(prices, [20.0, 19.0, 18.0])

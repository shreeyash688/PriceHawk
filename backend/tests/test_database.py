from database import db
from exceptions import DuplicateProductError, ProductNotFoundError
from tests.helpers import BOOK_URL, DatabaseTestCase

EMAIL = "a@x.com"


class DatabaseTests(DatabaseTestCase):
    def test_create_and_read(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0, EMAIL)
        row = db.get_product(product_id)
        self.assertEqual(row["title"], "Book A")
        self.assertEqual(row["tracking_active"], 1)
        self.assertEqual(len(db.get_all_products()), 1)

    def test_update(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0, EMAIL)
        db.update_target_price(product_id, 12.0)
        db.set_tracking_active(product_id, False)
        row = db.get_product(product_id)
        self.assertEqual(row["target_price"], 12.0)
        self.assertEqual(row["tracking_active"], 0)

    def test_delete_also_removes_history(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0, EMAIL)
        db.add_price_history(product_id, 20.0)
        db.delete_product(product_id)
        with self.assertRaises(ProductNotFoundError):
            db.get_product(product_id)
        self.assertEqual(list(db.iter_price_history()), [])

    def test_same_book_different_emails_allowed(self):
        db.add_product("Book A", BOOK_URL, 20.0, 15.0, "a@x.com")
        db.add_product("Book A", BOOK_URL, 20.0, 15.0, "b@x.com")  # no error
        self.assertEqual(len(db.get_all_products()), 2)
        self.assertEqual(len(db.get_all_products("a@x.com")), 1)
        self.assertEqual(db.count_products_for_email("b@x.com"), 1)

    def test_history_can_be_filtered_by_email(self):
        first = db.add_product("Book A", BOOK_URL, 20.0, 15.0, "a@x.com")
        second = db.add_product("Book A", BOOK_URL, 20.0, 15.0, "b@x.com")
        db.add_price_history(first, 20.0)
        db.add_price_history(second, 19.0)
        rows = list(db.iter_price_history(email="b@x.com"))
        self.assertEqual([row["price"] for row in rows], [19.0])

    def test_old_database_gives_clear_error(self):
        import sqlite3
        import config
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DROP TABLE price_history")
        conn.execute("DROP TABLE products")
        conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, url TEXT)")  # old layout
        conn.commit()
        conn.close()
        with self.assertRaises(RuntimeError):
            db.init_db()

    def test_duplicate_url_rejected(self):
        db.add_product("Book A", BOOK_URL, 20.0, 15.0, EMAIL)
        with self.assertRaises(DuplicateProductError):
            db.add_product("Book A again", BOOK_URL, 20.0, 15.0, EMAIL)

    def test_missing_product(self):
        with self.assertRaises(ProductNotFoundError):
            db.get_product(999)
        with self.assertRaises(ProductNotFoundError):
            db.delete_product(999)

    def test_history_generator(self):
        product_id = db.add_product("Book A", BOOK_URL, 20.0, 15.0, EMAIL)
        for price in (20.0, 19.0, 18.0):
            db.add_price_history(product_id, price)
        prices = [row["price"] for row in db.iter_price_history(product_id, batch_size=2)]
        self.assertEqual(prices, [20.0, 19.0, 18.0])

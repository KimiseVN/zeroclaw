"use client";
import { useCart } from "@/lib/cart-context";
import Link from "next/link";
import styles from "./CartDrawer.module.css";

export default function CartDrawer() {
  const { item, cartOpen, setCartOpen, removeFromCart } = useCart();

  return (
    <>
      {/* Backdrop */}
      <div
        className={`${styles.backdrop} ${cartOpen ? styles.open : ""}`}
        onClick={() => setCartOpen(false)}
      />

      {/* Drawer */}
      <aside className={`${styles.drawer} ${cartOpen ? styles.open : ""}`}>
        <div className={styles.head}>
          <span className={styles.title}>Your Cart</span>
          <button className={styles.closeBtn} onClick={() => setCartOpen(false)}>✕</button>
        </div>

        <div className={styles.body}>
          {!item ? (
            <div className={styles.empty}>
              <p>Cart is empty.</p>
              <p style={{ marginTop: 8 }}>
                <a href="/#pricing" onClick={() => setCartOpen(false)}>Browse plans →</a>
              </p>
            </div>
          ) : (
            <div className={styles.item}>
              <div className={styles.itemHead}>
                <span className={styles.itemName}>{item.plan.label.en}</span>
                <button className={styles.removeBtn} onClick={removeFromCart} title="Remove">✕</button>
              </div>

              <div className={styles.prices}>
                <div className={styles.priceRow}>
                  <span className={styles.priceLabel}>Price</span>
                  <div style={{ textAlign: "right" }}>
                    <div className={styles.priceVal}>${item.plan.usd.toFixed(2)}</div>
                    <div className={styles.priceVnd}>≈ {item.plan.vnd.toLocaleString("vi-VN")}đ</div>
                  </div>
                </div>
              </div>

              <div className={styles.features}>
                {item.plan.features.en.map(f => (
                  <div key={f} className={styles.feature}>{f}</div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className={styles.foot}>
          {item && (
            <>
              <div className={styles.total}>
                <span>Total</span>
                <span className={styles.totalVal}>${item.plan.usd.toFixed(2)}</span>
              </div>
              <Link
                href="/checkout/"
                className={`btn btn-primary ${styles.checkoutBtn}`}
                onClick={() => setCartOpen(false)}
              >
                Checkout →
              </Link>
            </>
          )}
          {!item && (
            <Link
              href="/#pricing"
              className={`btn btn-ghost ${styles.checkoutBtn}`}
              onClick={() => setCartOpen(false)}
            >
              View Plans
            </Link>
          )}
        </div>
      </aside>
    </>
  );
}

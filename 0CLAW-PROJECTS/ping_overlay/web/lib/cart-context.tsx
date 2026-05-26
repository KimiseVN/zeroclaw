"use client";
import {
  createContext, useContext, useState, useEffect,
  useCallback, type ReactNode,
} from "react";
import type { Plan } from "@/lib/plans";

export type CartItem = { plan: Plan };

type CartCtx = {
  item:         CartItem | null;
  cartOpen:     boolean;
  setCartOpen:  (v: boolean) => void;
  addToCart:    (plan: Plan) => void;
  removeFromCart: () => void;
  clearCart:    () => void;
};

const CartContext = createContext<CartCtx | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [item,     setItem]     = useState<CartItem | null>(null);
  const [cartOpen, setCartOpen] = useState(false);

  // Rehydrate from localStorage
  useEffect(() => {
    try {
      const s = localStorage.getItem("wwm_cart");
      if (s) setItem(JSON.parse(s));
    } catch {}
  }, []);

  const addToCart = useCallback((plan: Plan) => {
    const next = { plan };
    setItem(next);
    localStorage.setItem("wwm_cart", JSON.stringify(next));
    setCartOpen(true);
  }, []);

  const removeFromCart = useCallback(() => {
    setItem(null);
    localStorage.removeItem("wwm_cart");
  }, []);

  const clearCart = useCallback(() => {
    setItem(null);
    localStorage.removeItem("wwm_cart");
  }, []);

  return (
    <CartContext.Provider value={{ item, cartOpen, setCartOpen, addToCart, removeFromCart, clearCart }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be inside CartProvider");
  return ctx;
}

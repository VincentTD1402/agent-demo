import { BrowserRouter, Route, Routes } from "react-router-dom";
import { SiteLayout } from "./components/site-layout";
import { CartProvider } from "./lib/cart";
import { ChatBridgeProvider } from "./lib/chat-context";
import CartPage from "./pages/cart-page";
import HomePage from "./pages/home-page";
import ProductPage from "./pages/product-page";

export default function App() {
  return (
    <BrowserRouter>
      <CartProvider>
        <ChatBridgeProvider>
          <Routes>
            <Route element={<SiteLayout />}>
              <Route index element={<HomePage />} />
              <Route path="san-pham/:slug" element={<ProductPage />} />
              <Route path="gio-hang" element={<CartPage />} />
              <Route path="*" element={<p className="error">Không tìm thấy trang.</p>} />
            </Route>
          </Routes>
        </ChatBridgeProvider>
      </CartProvider>
    </BrowserRouter>
  );
}

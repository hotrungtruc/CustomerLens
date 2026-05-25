import "./globals.css";
import { Playfair_Display, Space_Grotesk } from "next/font/google";

const displayFont = Playfair_Display({
  subsets: ["latin", "vietnamese"],
  variable: "--font-display",
});

const bodyFont = Space_Grotesk({
  subsets: ["latin", "vietnamese"],
  variable: "--font-body",
});

export const metadata = {
  title: "He thong nhan dien khuon mat",
  description: "Giao dien diem danh khuon mat",
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi" className={`${displayFont.variable} ${bodyFont.variable}`}>
      <body>{children}</body>
    </html>
  );
}

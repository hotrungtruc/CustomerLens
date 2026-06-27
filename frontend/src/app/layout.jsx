import "./globals.css";
import { Inter, DM_Sans } from "next/font/google";
import MobileNav from "../components/MobileNav";
import ServerGate from "../components/ServerGate";

const displayFont = DM_Sans({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
});

const bodyFont = Inter({
  subsets: ["latin"],
  variable: "--font-body",
});

export const metadata = {
  title: "Front Desk AI",
  description:
    "Smart front-door AI dashboard for camera monitoring and guest tracking.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi" className={`${displayFont.variable} ${bodyFont.variable}`}>
      <body className="h-full antialiased">
        <MobileNav />
        <div className="h-dvh overflow-hidden pt-12 lg:pt-0">{children}</div>
      </body>
    </html>
  );
}

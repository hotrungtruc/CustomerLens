import "./globals.css";
import { Inter, DM_Sans } from "next/font/google";
import MobileNav from "../components/MobileNav";
import { AppProvider } from "../context/AppContext";

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
  title: "CustomerLens",
  description:
    "CustomerLens — Production AI Camera Intelligence and Visitor Recognition Dashboard.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${displayFont.variable} ${bodyFont.variable}`}>
      <body className="h-full antialiased bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 transition-colors duration-200">
        <AppProvider>
          <MobileNav />
          <div className="h-dvh overflow-hidden pt-12 lg:pt-0">{children}</div>
        </AppProvider>
      </body>
    </html>
  );
}

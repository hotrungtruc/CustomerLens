"use client";

import CameraStream from "../components/CameraStream";
import CustomerInfoCard from "../components/CustomerInfoCard";
import { useCustomerDetection } from "../hooks/useCustomerDetection";

export default function HomePage() {
  const {
    status,
    customer,
    message,
    checkIn,
    checkInState,
    error,
  } = useCustomerDetection();

  return (
    <main className="min-h-screen px-6 py-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-10 text-center">
          <p className="text-sm uppercase tracking-[0.4em] text-copper">Front Desk</p>
          <h1 className="mt-3 text-4xl font-semibold text-ink md:text-5xl">
            Smart Front-door AI
          </h1>
          <p className="mt-4 text-base text-ink/70">
            Monitor the entrance camera and refresh customer details in real time.
          </p>
        </header>

        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="panel p-6 animate-floatIn">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl">Camera</h2>
              <span className="rounded-full bg-clay px-3 py-1 text-xs uppercase tracking-wide text-ink">
                Live
              </span>
            </div>
            <CameraStream />
          </section>

          <section className="panel p-6 animate-floatIn">
            <CustomerInfoCard
              status={status}
              customer={customer}
              message={message}
              checkIn={checkIn}
              checkInState={checkInState}
              error={error}
            />
          </section>
        </div>
      </div>
    </main>
  );
}

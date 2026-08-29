import { CheckoutPageContent } from "@/components/CheckoutPageContent";

export default function DemoCheckoutPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-2xl font-semibold text-[var(--rf-ink)]">
        Checkout
      </h1>
      <div className="mt-6">
        <CheckoutPageContent />
      </div>
    </main>
  );
}

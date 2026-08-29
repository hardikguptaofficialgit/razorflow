import { CartPageContent } from "@/components/CartPageContent";

export default function DemoCartPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-2xl font-semibold text-[var(--rf-ink)]">
        Your cart
      </h1>
      <div className="mt-6">
        <CartPageContent />
      </div>
    </main>
  );
}

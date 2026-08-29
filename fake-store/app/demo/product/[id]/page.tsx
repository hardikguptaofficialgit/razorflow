import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AddToCartButton } from "@/components/AddToCartButton";
import { CATEGORY_LABELS } from "@/data/types";
import { demoRoutes } from "@/lib/demo-routes";
import { formatPrice } from "@/lib/format";
import { getProductById } from "@/lib/products";

interface ProductPageProps {
  params: Promise<{ id: string }>;
}

export default async function DemoProductPage({ params }: ProductPageProps) {
  const { id } = await params;
  const product = getProductById(id);
  if (!product) {
    notFound();
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <Link
        href={demoRoutes.home}
        className="text-sm font-medium text-[var(--rf-muted)] hover:text-[var(--rf-ink)]"
      >
        ← Back to shop
      </Link>

      <div className="mt-6 grid gap-8 md:grid-cols-2">
        <div className="relative aspect-square overflow-hidden rounded-2xl bg-[rgba(236,234,243,0.65)]">
          <Image
            src={product.imageUrl}
            alt={product.name}
            fill
            sizes="(max-width: 768px) 100vw, 50vw"
            className="object-contain p-6"
            priority
          />
        </div>

        <div className="space-y-4">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--rf-muted)]">
            {CATEGORY_LABELS[product.category]}
          </p>
          <h1
            className="font-display text-3xl font-semibold text-[var(--rf-ink)]"
            data-rf-product-title
          >
            {product.name}
          </h1>
          <p className="text-[var(--rf-muted)]">{product.description}</p>
          <p
            className="font-display text-3xl font-semibold text-[var(--rf-ink)]"
            data-rf-product-price
          >
            {formatPrice(product.price)}
          </p>
          <AddToCartButton productId={product.id} stock={product.stock} />
        </div>
      </div>
    </main>
  );
}

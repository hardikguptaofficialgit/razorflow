import { OrderDetailPageContent } from "@/components/OrderDetailPageContent";

interface OrderDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function DemoAccountOrderDetailPage({
  params,
}: OrderDetailPageProps) {
  const { id } = await params;
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <OrderDetailPageContent orderId={id} />
    </main>
  );
}

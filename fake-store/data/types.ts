export const PRODUCT_CATEGORIES = [
  "electronics",
  "personal-care",
  "fashion",
  "snacks",
] as const;

export type ProductCategory = (typeof PRODUCT_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<ProductCategory, string> = {
  electronics: "Electronics",
  "personal-care": "Personal care",
  fashion: "Fashion",
  snacks: "Snacks",
};

export interface Product {
  id: string;
  name: string;
  description: string;
  price: number;
  category: ProductCategory;
  imageUrl: string;
  stock: number;
  rating?: number;
}

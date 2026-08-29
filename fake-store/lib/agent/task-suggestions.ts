/** UI-only quick prompts — not used by agent logic. */

export type TaskSuggestion = {
  id: string;
  label: string;
  task: string;
  category: "search" | "shopping" | "compare" | "cart" | "checkout";
};

export const TASK_SUGGESTIONS: TaskSuggestion[] = [
  {
    id: "search-shampoo",
    label: "Search shampoo under ₹300",
    task: "search for shampoo under ₹300",
    category: "search",
  },
  {
    id: "compare-earbuds",
    label: "Compare wireless earbuds",
    task: "find and compare wireless earbuds on this site",
    category: "compare",
  },
  {
    id: "multi-watch-buds",
    label: "Add watch + earbuds",
    task: "add a watch and earbuds to my cart",
    category: "shopping",
  },
  {
    id: "add-snacks",
    label: "Add snacks under ₹200",
    task: "add good snacks under ₹200 to my cart",
    category: "shopping",
  },
  {
    id: "view-cart",
    label: "Open my cart",
    task: "open my cart",
    category: "cart",
  },
  {
    id: "checkout",
    label: "Proceed to checkout",
    task: "proceed to checkout",
    category: "checkout",
  },
];

export function suggestionsForPhase(phase: string, hasRun: boolean): TaskSuggestion[] {
  if (hasRun && phase !== "idle" && phase !== "complete") {
    return TASK_SUGGESTIONS.filter((s) => s.category === "cart" || s.category === "checkout");
  }
  return TASK_SUGGESTIONS;
}

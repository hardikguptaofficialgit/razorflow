import { redirect } from "next/navigation";

interface SignupPageProps {
  searchParams: Promise<{ next?: string }>;
}

export default async function SignupPage({ searchParams }: SignupPageProps) {
  const { next } = await searchParams;
  const url = new URLSearchParams({ auth: "signup" });
  if (next?.startsWith("/")) {
    url.set("next", next);
  }
  redirect(`/?${url.toString()}`);
}

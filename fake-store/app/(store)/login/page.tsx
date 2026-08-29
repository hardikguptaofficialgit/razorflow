import { redirect } from "next/navigation";

interface LoginPageProps {
  searchParams: Promise<{ next?: string }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { next } = await searchParams;
  const url = new URLSearchParams({ auth: "login" });
  if (next?.startsWith("/")) {
    url.set("next", next);
  }
  redirect(`/?${url.toString()}`);
}

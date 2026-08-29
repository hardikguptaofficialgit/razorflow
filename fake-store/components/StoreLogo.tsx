import Image from "next/image";
import Link from "next/link";

export const LOGO_PATH = "/logo.png";

interface StoreLogoProps {
  size?: number;
  className?: string;
  priority?: boolean;
}

/** RazorFlow logo mark from brand assets. */
export function StoreLogo({
  size = 32,
  className = "",
  priority = false,
}: StoreLogoProps) {
  return (
    <Image
      src={LOGO_PATH}
      alt="RazorFlow"
      width={size}
      height={size}
      priority={priority}
      className={`shrink-0 object-contain ${className}`.trim()}
    />
  );
}

interface StoreLogoLockupProps {
  href: string;
  size?: number;
  className?: string;
  wordmarkClassName?: string;
  priority?: boolean;
}

/** Logo + RazorFlow wordmark for headers and nav. */
export function StoreLogoLockup({
  href,
  size = 32,
  className = "",
  wordmarkClassName = "",
  priority = false,
}: StoreLogoLockupProps) {
  return (
    <Link
      href={href}
      className={`group inline-flex shrink-0 items-center gap-2.5 ${className}`.trim()}
    >
      <StoreLogo
        size={size}
        priority={priority}
        className="rounded-[10px] transition-transform duration-200 group-hover:scale-[1.02]"
      />
      <span
        className={
          wordmarkClassName ||
          "font-display text-[19px] font-bold tracking-[-0.04em] text-[var(--rf-ink)]"
        }
      >
        RazorFlow
      </span>
    </Link>
  );
}

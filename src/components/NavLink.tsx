"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      className={`px-3 py-1.5 rounded-[10px] text-sm font-medium transition ${
        active
          ? "text-[#DC2626] bg-[#FEF2F2]"
          : "text-[#334155] hover:text-[#0F172A] hover:bg-slate-100"
      }`}
    >
      {label}
    </Link>
  );
}

export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill={dark ? "#0a2420" : "#13443c"} />
        <path d="M8 22V10l5 7 5-7v12" stroke="#7bbcae" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="23.5" cy="20.5" r="2.2" fill="#d2612f" />
      </svg>
      <div className="leading-none">
        <div className={dark ? "text-lg font-extrabold tracking-tight text-pine-950" : "text-lg font-extrabold tracking-tight text-white"}>mise</div>
        <div className={dark ? "text-[10px] font-medium text-stone-500" : "text-[10px] font-medium text-pine-300/80"}>gestão de bares e restaurantes</div>
      </div>
    </div>
  );
}
